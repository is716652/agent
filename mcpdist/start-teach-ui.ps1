# teach_ui 启动脚本（PowerShell）
# 用法：右键“使用 PowerShell 运行”或在 PowerShell 中执行 .\start-teach-ui.ps1
# 说明：
# 1) 若未设置 PORT，则默认使用 5001；可自行修改端口
# 2) 如需设置 API Key，取消对应行注释并填入你的 Key

param(
    [int]$Port = $env:PORT -as [int] -or 5001
)

# 若外部已有 PORT，则尊重外部；否则使用参数/默认值
if (-not $env:PORT) { $env:PORT = [string]$Port }

# 可选：设置 Key（按需启用一项或两项）
# $env:DEEPSEEK_API_KEY = "在此填入你的Key"
# $env:OPENAI_API_KEY   = "在此填入你的Key"

# 启动 UI，可在需要时改为 -NoNewWindow 以保持在同一窗口
Start-Process -FilePath "$PSScriptRoot/teach_ui.exe"