import os
import sys
import subprocess
import shutil
from pathlib import Path
from flask import Flask, render_template, request, redirect, url_for, send_from_directory, flash

app = Flask(__name__)
# 简单随机密钥用于Flash消息（不会用于持久化会话）
app.secret_key = os.urandom(16)

# 定位项目与输出目录
BASE_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = BASE_DIR / 'output'
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

@app.route('/', methods=['GET', 'POST'])
def index():
    if request.method == 'POST':
        course = (request.form.get('course') or '').strip()
        weeks_str = (request.form.get('weeks') or '').strip()
        parts = (request.form.get('parts') or '').strip()
        exclude = (request.form.get('exclude') or '').strip()
        features = (request.form.get('features') or '').strip()
        model = (request.form.get('model') or '').strip()
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

        # 设置环境变量（仅进程级，避免落盘）
        env = os.environ.copy()
        env['OPENAI_API_KEY'] = api_key
        env['DEEPSEEK_API_KEY'] = api_key
        if model.startswith('deepseek'):
            env['OPENAI_BASE_URL'] = 'https://api.deepseek.com'
        elif model.startswith('gpt') or model.startswith('o'):
            # 使用 OpenAI 官方时，可不设置 BASE_URL 或根据实际代理设置
            env.pop('OPENAI_BASE_URL', None)
        # 保证 UTF-8 输出
        env['PYTHONIOENCODING'] = 'utf-8'

        # 构建命令
        cmd = [
            sys.executable,
            str(BASE_DIR / 'build_course_docs.py'),
            '--course', course,
            '--weeks', str(weeks),
            '--model', model or 'deepseek-chat',
        ]
        if parts:
            cmd += ['--parts', parts]
        if exclude:
            cmd += ['--exclude', exclude]
        if features:
            cmd += ['--features', features]

        # 运行脚本
        try:
            proc = subprocess.run(cmd, env=env, cwd=str(BASE_DIR), capture_output=True, text=True, encoding='utf-8')
        except Exception as e:
            flash(f'执行出错：{e}')
            return render_template('index.html')

        if proc.returncode != 0:
            flash('生成失败：' + (proc.stderr or proc.stdout))
            return render_template('index.html')

        # 基于模板生成“教案模板标记值-课程名称.md”
        try:
            tpl_path = BASE_DIR / 'templates' / '教案模板标记值.md'
            if tpl_path.exists():
                tpl_text = tpl_path.read_text(encoding='utf-8')
                # 替换占位符
                replacements = {
                    '{授课科目}': course,
                    '{总周数}': str(weeks),
                    '{授课老师}': teacher,
                    '{授课班级}': class_name,  # 新增：来自表单
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
            # 不阻断主流程，仅提示
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
            return render_template('index.html', raw_output=proc.stdout)

        # 新增：将 output 结果拷贝到 IndependentRunningPackage/data 并执行单文件脚本，随后将结果放入 docs
        try:
            irp_dir = BASE_DIR / 'IndependentRunningPackage'
            data_dir = irp_dir / 'data'
            data_dir.mkdir(parents=True, exist_ok=True)

            # 拷贝三份文件（存在则覆盖）
            to_copy = [
                (OUTPUT_DIR / marks_file),
                (OUTPUT_DIR / plan_file),
                (OUTPUT_DIR / syllabus_file),
            ]
            for src in to_copy:
                if src.exists():
                    shutil.copy2(str(src), str(data_dir / src.name))

            # 执行独立运行包脚本
            script_path = irp_dir / 'build_word_from_templates.py'
            if script_path.exists():
                proc2 = subprocess.run(
                    [sys.executable, str(script_path)],
                    cwd=str(irp_dir),
                    capture_output=True,
                    text=True,
                    encoding='utf-8'
                )
                if proc2.returncode != 0:
                    flash('教案 Word 生成脚本执行失败：' + (proc2.stderr or proc2.stdout))
                else:
                    # 将生成结果复制到 docs 目录
                    docs_dir = BASE_DIR / 'docs'
                    docs_dir.mkdir(parents=True, exist_ok=True)
                    expected_name = f"教案-{course}.docx"
                    src_docx = irp_dir / expected_name
                    target_path = docs_dir / expected_name
                    found = False
                    if src_docx.exists():
                        shutil.copy2(str(src_docx), str(target_path))
                        found = True
                    else:
                        # 兜底：按名称模式查找
                        for p in irp_dir.glob('教案-*.docx'):
                            if course in p.stem:
                                shutil.copy2(str(p), str(target_path))
                                found = True
                                break
                    # 如果已经复制成功，则将下载链接加入返回
                    if found and target_path.exists():
                        try:
                            links['word'] = url_for('download_docs', filename=expected_name)
                        except Exception:
                            pass
                    if not found:
                        flash('未在独立运行包目录找到生成的教案 Word 文件。')
            else:
                flash('未找到独立运行包脚本：IndependentRunningPackage/build_word_from_templates.py')
        except Exception as e:
            flash(f'提示：自动汇入独立运行包并生成 Word 失败：{e}')

        return render_template('result.html', course=course, links=links, raw_output=proc.stdout)

    return render_template('index.html')


@app.route('/download/<path:filename>')
def download(filename):
    # 从 output 目录提供下载
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


# 新增：从 docs 目录下载教案 Word 文件
@app.route('/download-docs/<path:filename>')
def download_docs(filename):
    docs_dir = BASE_DIR / 'docs'
    return send_from_directory(docs_dir, filename, as_attachment=True)


if __name__ == '__main__':
    port = int(os.environ.get('PORT') or os.environ.get('FLASK_RUN_PORT') or 89)
    app.run(host='0.0.0.0', port=port)