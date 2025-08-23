import os
import sys
import subprocess
import shutil
import json
import threading
import webbrowser
import re
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash

# 保证项目根目录在 sys.path 中，避免直接运行时找不到本地模块
try:
    _ROOT = Path(__file__).resolve().parents[1]
    if str(_ROOT) not in sys.path:
        sys.path.insert(0, str(_ROOT))
except Exception:
    pass

# Import generation utilities for in-process execution
from build_course_docs import (
    build_syllabus_messages,
    build_plan_messages,
    ensure_pure_json,
)
from generate_syllabus import call_llm

# Resolve runtime/base directories for both dev and frozen (PyInstaller)
IS_FROZEN = getattr(sys, 'frozen', False)
EXEC_DIR = Path(sys.executable).parent if IS_FROZEN else Path(__file__).resolve().parent
MEIPASS = Path(getattr(sys, '_MEIPASS', EXEC_DIR))
# Project root when running from source; when frozen, treat exec directory as base
BASE_DIR = (Path(__file__).resolve().parents[1] if not IS_FROZEN else EXEC_DIR)
# Template folder must work in both modes
TEMPLATE_DIR = (MEIPASS / 'UI' / 'templates') if IS_FROZEN else (Path(__file__).resolve().parent / 'templates')
# LLM template resources directory (syllabus_template.md, data_template.json)
LLM_TPL_DIR = (MEIPASS / 'templates') if IS_FROZEN else (BASE_DIR / 'templates')

app = Flask(__name__, template_folder=str(TEMPLATE_DIR))
# 简单随机密钥用于Flash消息（不会用于持久化会话）
app.secret_key = os.urandom(16)

# 定位输出与文档目录（随运行目录走，便于打包后可写）
OUTPUT_DIR = (BASE_DIR / 'output')
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DOCS_DIR = (BASE_DIR / 'docs')
DOCS_DIR.mkdir(parents=True, exist_ok=True)


def _detect_mcp_wrapper() -> Path:
    """Locate mcp_wrapper.exe packaged alongside the UI (or nearby)."""
    candidates = [
        EXEC_DIR / 'mcp_wrapper.exe',
        EXEC_DIR / 'dist' / 'mcp_wrapper.exe',
        MEIPASS / 'mcp_wrapper.exe',
        MEIPASS / 'dist' / 'mcp_wrapper.exe',
        # Dev fallbacks
        BASE_DIR / 'dist' / 'mcp_wrapper.exe',
        BASE_DIR / 'mcpdist' / 'mcp_wrapper.exe',
        BASE_DIR.parent / 'mcpdist' / 'mcp_wrapper.exe',
    ]
    for c in candidates:
        if c.is_file():
            return c
    raise FileNotFoundError('未找到 mcp_wrapper.exe，请确保它与 UI 可执行文件位于同一目录或 dist/mcpdist 目录下。')


def _contains_any(text: str, keywords: list[str]) -> bool:
    if not keywords:
        return False
    t = text.lower()
    for k in keywords:
        k = (k or '').strip()
        if not k:
            continue
        if k.lower() in t:
            return True
    return False


def _sanitize_markdown(md: str, excludes: list[str]) -> str:
    """移除包含排除关键词的行，弱化“串台”内容。"""
    if not excludes:
        return md
    lines = md.splitlines()
    kept = []
    for ln in lines:
        if _contains_any(ln, excludes):
            continue
        kept.append(ln)
    # 若全部被清空，则回退到原文，避免产物为空
    txt = "\n".join(kept).strip()
    return txt or md


@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        course = (request.form.get('course') or '').strip()
        weeks_str = (request.form.get('weeks') or '').strip()
        parts = (request.form.get('parts') or '').strip()
        exclude = (request.form.get('exclude') or '').strip()
        features = (request.form.get('features') or '').strip()
        action = (request.form.get('do') or 'generate').strip()  # 新增：动作（生成/清理）
        # 模型相关字段
        provider = (request.form.get('provider') or '').strip()  # deepseek/openai/siliconflow/custom
        model = (request.form.get('model') or '').strip()
        base_url_form = (request.form.get('base_url') or '').strip()
        api_key = (request.form.get('api_key') or '').strip()
        
        # 新增：授课信息字段
        teacher = (request.form.get('teacher') or '').strip()
        class_name = (request.form.get('class_name') or '').strip()
        location = (request.form.get('location') or '').strip()
        assessment = (request.form.get('assessment') or '').strip()
        class_size_raw = (request.form.get('class_size') or '').strip()
        weekly_hours = (request.form.get('weekly_hours') or '').strip()
        teaching_time = (request.form.get('teaching_time') or '').strip()

        # 校验
        if not course:
            flash('课程名称不能为空')
            return render_template('index.html')

        # 清理动作：仅需课程名，直接执行删除并返回
        if action == 'cleanup':
            try:
                removed = []
                # output 下的相关文件
                for pat in [f"{course}-教学大纲.md", f"{course}-*-data.json", f"{course}-data.json", f"教案模板标记值-{course}.md"]:
                    for p in OUTPUT_DIR.glob(pat):
                        try:
                            p.unlink()
                            removed.append(str(p))
                        except Exception:
                            pass
                # docs 下的相关文件（主成品 + 可能的带时间戳副本）
                for pat in [f"教案-{course}.docx", f"教案-{course}-*.docx"]:
                    for p in DOCS_DIR.glob(pat):
                        try:
                            p.unlink()
                            removed.append(str(p))
                        except Exception:
                            pass
                if removed:
                    flash(f"已清理 {len(removed)} 个与 ‘{course}’ 相关的输出文件。")
                else:
                    flash(f"未发现需清理的 ‘{course}’ 相关输出文件。")
            except Exception as e:
                flash(f"清理失败：{e}")
            return render_template('index.html')

        if not api_key:
            flash('API Key 不能为空')
            return render_template('index.html')
        try:
            weeks = int(weeks_str)
        except ValueError:
            flash('周数必须为整数')
            return render_template('index.html')

        # 服务器端对班级人数做健壮性校验（仅允许 1..99 的整数，不合法则置空）
        class_size = ''
        if class_size_raw.isdigit():
            n = int(class_size_raw)
            if 1 <= n < 100:
                class_size = str(n)

        # 设置环境变量（当前进程，供 call_llm 使用）
        # 统一使用 OPENAI_API_KEY，必要时兼容 DEEPSEEK_API_KEY
        os.environ['OPENAI_API_KEY'] = api_key
        # 根据 provider 控制 base_url 与 DEEPSEEK_API_KEY
        # 默认清理，避免遗留环境变量干扰
        os.environ.pop('OPENAI_BASE_URL', None)
        os.environ.pop('LLM_BASE_URL', None)
        os.environ.pop('DEEPSEEK_API_KEY', None)
        
        provider_norm = (provider or '').lower()
        resolved_base = ''
        if provider_norm == 'deepseek':
            resolved_base = 'https://api.deepseek.com'
            os.environ['DEEPSEEK_API_KEY'] = api_key  # 兼容旧逻辑
        elif provider_norm == 'openai':
            resolved_base = ''  # 官方无需 base_url
        elif provider_norm in ('siliconflow', 'custom'):
            resolved_base = base_url_form or ''
        else:
            # 兜底：根据模型名进行启发式
            if model.startswith('deepseek'):
                resolved_base = 'https://api.deepseek.com'
            else:
                resolved_base = base_url_form or ''
        if resolved_base:
            os.environ['OPENAI_BASE_URL'] = resolved_base
        os.environ['PYTHONIOENCODING'] = 'utf-8'

        # 读取 LLM 模板资源
        try:
            syllabus_tpl = (LLM_TPL_DIR / 'syllabus_template.md').read_text(encoding='utf-8')
            data_tpl = (LLM_TPL_DIR / 'data_template.json').read_text(encoding='utf-8')
        except Exception as e:
            flash(f'读取模板失败：{e}')
            return render_template('index.html')

        # 解析表单中的 parts/exclude
        parts_list = [s.strip() for s in parts.split(',') if s.strip()] if parts else None
        excludes_list_user = [s.strip() for s in exclude.split(',') if s.strip()] if exclude else []
        features_text = features or None

        # 基于课程名的自动排除词，减少“串台”内容
        cname = course.lower()
        auto_excludes: list[str] = []
        if any(k in cname for k in ['docker', '容器', '虚拟化', 'k8s', 'kubernetes']):
            auto_excludes = ['软件测试', '测试', '机器学习', '深度学习', '大数据', '数据挖掘', 'Hadoop', 'Spark', 'Selenium', '单元测试', '集成测试', '系统测试', '回归测试', '缺陷', '质量度量', '测试用例']
        elif any(k in cname for k in ['软件测试', '测试']):
            auto_excludes = ['机器学习', '深度学习', '大数据', '数据挖掘', 'Hadoop', 'Spark', 'Docker', '容器', '虚拟化', 'Kubernetes', 'K8s']
        # 合并用户与自动排除，去重
        excludes_list: list[str] = []
        for it in excludes_list_user + auto_excludes:
            if it and it not in excludes_list:
                excludes_list.append(it)

        # 第一阶段：生成教学大纲（Markdown）
        try:
            syllabus_msgs = build_syllabus_messages(
                course=course,
                weeks=weeks,
                parts=parts_list,
                excludes=excludes_list or None,
                template_text=syllabus_tpl,
                level='高职学生',
                features=features_text,
            )
            syllabus_md_raw = call_llm(syllabus_msgs, model=model or 'deepseek-chat')
            # 生成后在服务端做一次“排除词”行级清洗，进一步降低串台
            syllabus_md = _sanitize_markdown(syllabus_md_raw, excludes_list)
            # 若清洗后内容过少，回退原文
            if len(syllabus_md.strip()) < max(50, int(len(syllabus_md_raw) * 0.3)):
                syllabus_md = syllabus_md_raw
            syllabus_path = OUTPUT_DIR / f"{course}-教学大纲.md"
            syllabus_path.write_text(syllabus_md, encoding='utf-8')
        except Exception as e:
            flash(f'大纲生成失败：{e}')
            return render_template('index.html')

        # 第二阶段：根据大纲生成教案 JSON（基于清洗后的大纲）
        try:
            plan_msgs = build_plan_messages(
                course=course,
                weeks=weeks,
                syllabus_md=syllabus_md,
                data_template_text=data_tpl,
            )
            plan_json_text = call_llm(plan_msgs, model=model or 'deepseek-chat')
            plan_json_text = ensure_pure_json(plan_json_text)
            plan_obj = json.loads(plan_json_text)
            # 纠正关键字段
            if plan_obj.get('授课科目') != course:
                plan_obj['授课科目'] = course
            if plan_obj.get('总周数') != weeks:
                plan_obj['总周数'] = weeks
            weeks_list = plan_obj.get('周次') or []
            if not isinstance(weeks_list, list) or len(weeks_list) != weeks:
                fixed = []
                for i in range(weeks):
                    item = weeks_list[i] if i < len(weeks_list) else {}
                    fixed.append({
                        '周': i + 1,
                        '课题': item.get('课题', ''),
                        '教学目标': item.get('教学目标', ''),
                        '教学重点': item.get('教学重点', ''),
                        '教学难点': item.get('教学难点', ''),
                        '授课内容1': item.get('授课内容1', ''),
                        '授课内容2': item.get('授课内容2', ''),
                        '授课内容3': item.get('授课内容3', ''),
                        '授课内容4': item.get('授课内容4', ''),
                        '作业': item.get('作业', ''),
                    })
                plan_obj['周次'] = fixed
            plan_path = OUTPUT_DIR / f"{course}-{weeks}-data.json"
            plan_path.write_text(json.dumps(plan_obj, ensure_ascii=False, indent=2), encoding='utf-8')
        except Exception as e:
            flash(f'教案 JSON 生成失败：{e}')
            return render_template('index.html')

        # 基于模板生成“教案模板标记值-课程名称.md”（写入授课信息）
        try:
            tpl_path = LLM_TPL_DIR / '教案模板标记值.md'
            if tpl_path.exists():
                tpl_text = tpl_path.read_text(encoding='utf-8')
                replacements = {
                    '{授课科目}': course,
                    '{总周数}': str(weeks),
                    '{授课老师}': teacher,
                    '{授课班级}': class_name,
                    '{班级人数}': class_size,
                    '{授课时间}': teaching_time,
                    '{周学时}': (f"{weekly_hours} 学时/周" if weekly_hours else ''),
                    '{考核方式}': assessment,
                    '{授课地点}': location,
                }
                out_text = tpl_text
                for k, v in replacements.items():
                    out_text = out_text.replace(k, v)
                out_name = f"教案模板标记值-{course}.md"
                out_path = OUTPUT_DIR / out_name
                out_path.write_text(out_text, encoding='utf-8')
        except Exception as e:
            flash(f'提示：标记值文件生成时出现问题：{e}')

        # 生成的文件路径（根据命名规则）
        syllabus_file = f"{course}-教学大纲.md"
        plan_file = f"{course}-{weeks}-data.json"
        marks_file = f"教案模板标记值-{course}.md"

        links = {}
        if (OUTPUT_DIR / syllabus_file).exists():
            links['syllabus'] = url_for('download', filename=syllabus_file)
        if (OUTPUT_DIR / plan_file).exists():
            links['plan'] = url_for('download', filename=plan_file)
        if (OUTPUT_DIR / marks_file).exists():
            links['marks'] = url_for('download', filename=marks_file)

        if not links:
            flash('未找到生成的文件，请检查日志输出。')
            return render_template('index.html')

        # 使用 MCP 封装器调用底层 EXE，直接将 DOCX 输出到 docs 目录
        try:
            wrapper = _detect_mcp_wrapper()
            # 将三份输入复制到 EXE 所在目录，以避免底层 EXE 的 argparse 兼容性问题
            exe_dir = wrapper.parent
            try:
                shutil.copy2(str(OUTPUT_DIR / marks_file), str(exe_dir / marks_file))
            except Exception:
                pass
            try:
                shutil.copy2(str(OUTPUT_DIR / plan_file), str(exe_dir / plan_file))
            except Exception:
                pass
            try:
                shutil.copy2(str(OUTPUT_DIR / syllabus_file), str(exe_dir / syllabus_file))
            except Exception:
                pass

            # 仅传递输出目录与科目，让底层 EXE 自动发现输入
            exe_args = [
                str(wrapper),
                '--output-dir', str(DOCS_DIR),
                '--subject', course,
                # 显式传递三份输入，避免底层 EXE 在其运行目录中“抓错文件”
                '--md', str(OUTPUT_DIR / marks_file),
                '--json-data', str(OUTPUT_DIR / plan_file),
                '--syllabus', str(OUTPUT_DIR / syllabus_file),
                '--verbose'
            ]
            proc2 = subprocess.run(exe_args, cwd=str(BASE_DIR), capture_output=True)
            # 解析 JSON 输出
            stdout_text = ''
            try:
                stdout_text = proc2.stdout.decode('utf-8', errors='ignore') if isinstance(proc2.stdout, (bytes, bytearray)) else (proc2.stdout or '')
            except Exception:
                stdout_text = proc2.stdout if isinstance(proc2.stdout, str) else ''
            parsed = None
            for line in stdout_text.splitlines():
                s = (line or '').strip()
                if s.startswith('{') and s.endswith('}'):
                    try:
                        parsed = json.loads(s)
                    except Exception:
                        pass
            if proc2.returncode != 0 or not parsed or not parsed.get('ok'):
                err_tail = (proc2.stderr.decode('utf-8', errors='ignore') if isinstance(proc2.stderr, (bytes, bytearray)) else (proc2.stderr or ''))
                flash('教案 Word 生成失败：' + (err_tail or stdout_text[-400:]))
            else:
                expected_name = f"教案-{course}.docx"
                target_path = DOCS_DIR / expected_name
                if not target_path.exists() and parsed.get('files'):
                    try:
                        for f in parsed['files']:
                            p = Path(f)
                            if p.exists() and p.suffix.lower() == '.docx':
                                shutil.copy2(str(p), str(target_path))
                                break
                    except Exception:
                        pass
                if target_path.exists():
                    try:
                        links['word'] = url_for('download_docs', filename=expected_name)
                    except Exception:
                        pass
                else:
                    flash('未找到生成的教案 Word 文件。')
        except Exception as e:
            flash(f'提示：通过 MCP 封装器生成 Word 失败：{e}')

        return render_template('result.html', course=course, links=links)

    return render_template('index.html')


@app.route('/download/<path:filename>')
def download(filename):
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


@app.route('/download-docs/<path:filename>')
def download_docs(filename):
    return send_from_directory(DOCS_DIR, filename, as_attachment=True)


if __name__ == '__main__':
    port = int(os.environ.get('PORT') or os.environ.get('FLASK_RUN_PORT') or 89)
    # 自动打开浏览器（延迟以等待服务启动）
    threading.Timer(0.8, lambda: webbrowser.open_new_tab(f'http://127.0.0.1:{port}/')).start()
    app.run(host='127.0.0.1', port=port, threaded=True)