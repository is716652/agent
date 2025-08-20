# 教学大纲与教案生成器

一个基于 Flask 的简易 UI，用大模型一键生成课程教学大纲（Markdown）与教案数据（JSON）。

## 功能概览
- 表单填写后，生成两类产物并保存在 `output/` 目录：
  - `课程名称-教学大纲.md`
  - `课程名称-周数-data.json`（例如：`软件测试-18-data.json`）
- 支持输入：课程名称、总周数、排除项、教学大纲的功能说明（不作为排除项）、模型选择（DeepSeek 或 OpenAI）与 API Key。
- 自动处理“最后一周复习与综合提升”的建议：
  - 18 周时：固定“最后一周复习与综合提升”。
  - 20 周或其他周数：给出“最后一周复习与综合提升”的安排建议。
- API Key 仅在进程环境变量中使用，不会写入磁盘。

## 目录结构（关键）
```
agent/
├── UI/
│   ├── app.py                    # Flask 应用入口（Web 表单、生成与下载）
│   └── templates/
│       ├── index.html            # 表单页面（含功能说明、多模型、动态周数提示）
│       └── result.html           # 结果页（产物下载链接 + 运行日志）
├── build_course_docs.py          # 实际调用大模型生成大纲与教案的脚本
├── generate_syllabus.py          # 生成大纲的辅助脚本
├── templates/
│   ├── data_template.json        # 教案 JSON 模板
│   └── syllabus_template.md      # 教学大纲 Markdown 模板
├── requirements.txt              # 依赖清单
├── scripts/
│   ├── set-git-proxy.ps1         # 仓库级设置 Git 代理
│   └── unset-git-proxy.ps1       # 仓库级取消 Git 代理
└── output/                       # 生成结果（运行后出现）
```

## 安装依赖
建议使用本机 Python（或你的虚拟环境）执行：

```powershell
# 在项目根目录执行
pip install -r requirements.txt
```

## 启动 UI
默认端口 5000，可通过环境变量覆盖：

```powershell
# 方式一：使用系统 python（已安装依赖）
$env:PORT = "5000"        # 可改为 5001/5002...
python .\UI\app.py

# 方式二：指定虚拟环境 python 可执行文件
$env:PORT = "5001"
& "d:\Trae_Project\agent\VENV\agent-env\Scripts\python.exe" "d:\Trae_Project\agent\UI\app.py"
```

启动成功后访问：
- http://127.0.0.1:5000/（或你设置的端口）

## 使用说明
1. 打开表单页，填写：
   - 课程名称（必填）
   - 总周数（必填，18/20/其他均可，页面有动态提示）
   - 排除项（可空，逗号分隔）
   - 教学大纲的功能说明（可空，不作为排除项）
   - 大模型选择：DeepSeek（deepseek-chat）或 OpenAI（gpt-4o-mini）
   - API Key（必填）
2. 提交后，等待生成完成，跳转到结果页，点击链接下载文件。

说明：
- DeepSeek 模式下，会自动设置 `OPENAI_BASE_URL=https://api.deepseek.com`。
- Key 仅在子进程环境变量中使用，不会写入磁盘或日志。

## 命令行直接生成（可选）
无需 UI，直接用脚本生成：

```powershell
# 以 DeepSeek 为例
$env:OPENAI_API_KEY = "你的Key"
$env:DEEPSEEK_API_KEY = "你的Key"
$env:OPENAI_BASE_URL = "https://api.deepseek.com"
python .\build_course_docs.py --course "软件测试" --weeks 18 --model deepseek-chat --exclude "ChatGPT,生成代码" --features "强调项目驱动与实训"

# 以 OpenAI 为例（通常无需设置 OPENAI_BASE_URL）
$env:OPENAI_API_KEY = "你的Key"
python .\build_course_docs.py --course "软件测试" --weeks 18 --model gpt-4o-mini
```

生成后，产物位于 `output/`：
- `课程名称-教学大纲.md`
- `课程名称-周数-data.json`

也可通过 UI 下载接口：
- `GET /download/<filename>`（例如 `/download/软件测试-18-data.json`）

## 代理与推送（可选）
仓库已提供便捷脚本，仅影响当前仓库：

```powershell
# 设置仓库级代理（默认 127.0.0.1:10808）
.\scripts\set-git-proxy.ps1
# 或自定义端口
.\scripts\set-git-proxy.ps1 -Proxy "http://127.0.0.1:7890"

# 取消仓库级代理
.\scripts\unset-git-proxy.ps1
```

## 常见问题
- 端口占用：
  - 设置 `PORT`（或 `FLASK_RUN_PORT`）到其他端口后再启动。
- PowerShell 运行脚本被拦截：
  - 临时放行当前进程：`Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass`
- 推送 GitHub 超时：
  - 使用上面的仓库级代理脚本，或在 Git 中设置全局/仓库代理。

## 文件命名规则摘要
- 大纲：`课程名称-教学大纲.md`
- 教案 JSON：`课程名称-周数-data.json`（示例：`软件测试-18-data.json`）

## 安全提示
- 不要将 API Key 写入代码或仓库。
- 仅在运行时通过环境变量传入，完成后可清除当前会话的环境变量。

---
如需进一步定制（UI 两列布局、更大输入区、模板个性化、接入更多模型等），欢迎提交 Issue 或 PR。