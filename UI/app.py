import os
import sys
import subprocess
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

        # 生成的文件路径（根据命名规则）
        syllabus_file = f"{course}-教学大纲.md"
        plan_file = f"{course}-{weeks}-data.json"
        links = []
        if (OUTPUT_DIR / syllabus_file).exists():
            links.append({'name': syllabus_file, 'url': url_for('download', filename=syllabus_file)})
        if (OUTPUT_DIR / plan_file).exists():
            links.append({'name': plan_file, 'url': url_for('download', filename=plan_file)})

        if not links:
            flash('未找到生成的文件，请检查日志输出。')
            return render_template('index.html', raw_output=proc.stdout)

        return render_template('result.html', links=links, raw_output=proc.stdout)

    return render_template('index.html')


@app.route('/download/<path:filename>')
def download(filename):
    # 从 output 目录提供下载
    return send_from_directory(OUTPUT_DIR, filename, as_attachment=True)


if __name__ == '__main__':
    port = int(os.environ.get('PORT') or os.environ.get('FLASK_RUN_PORT') or 5000)
    app.run(host='0.0.0.0', port=port)