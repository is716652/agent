@echo off
setlocal

rem ======== teach_ui 启动脚本（Batch）========
rem 说明：
rem 1) 如果未事先在系统或当前窗口设置 PORT，这里默认使用 5001；
rem 2) 如需固定端口，修改下行的数值即可；
rem 3) 如需设置 API Key，可取消相应行的注释并填入你的 Key；

if not defined PORT set "PORT=5001"

rem ==== 可选：在此处填写你的 Key（二选一，或都不填走已有环境变量）====
rem set "DEEPSEEK_API_KEY=在此填入你的Key"
rem set "OPENAI_API_KEY=在此填入你的Key"
rem ==============================================================

rem 启动 UI（继承上述环境变量）；使用 start 以便不阻塞当前窗口
start "" "%~dp0teach_ui.exe"

endlocal