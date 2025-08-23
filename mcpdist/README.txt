mcp_wrapper.exe + build_word.exe 使用说明

一、目录结构
- mcpdist/
  - mcp_wrapper.exe  MCP 封装器（统一入口，调用 build_word.exe 并输出 JSON）
  - build_word.exe   教案生成器（支持零参数自动发现与 CLI 参数）

二、快速开始
- 零参数自动发现：
  直接双击或在命令行运行 mcp_wrapper.exe
  - 自动定位同目录的 build_word.exe
  - build_word.exe 将按命名规则自动发现输入（见「三、输入规则」）
  - 生成 DOCX 到当前目录（或你指定的输出目录）
  - mcp_wrapper.exe 在标准输出打印一行 JSON 结果

- 指定输出目录（推荐）：
  .\mcp_wrapper.exe --output-dir ".\output" --verbose

三、输入规则（自动发现模式）
若未传入 --md / --json-data / --syllabus 参数，build_word.exe 会从其所在目录按以下模式查找：
- 教案标记 MD：教案模板标记值-*.md
- 数据 JSON：*-data.json
- 教学大纲（可选）：教学大纲*.md
若需精确控制输入，请转用路径模式传参（见下节）。

四、CLI 参数（mcp_wrapper.exe）
- 路径模式（传递给底层 exe）：
  --md <path>                指定教案标记 MD
  --json-data <path>         指定数据 JSON
  --syllabus <path>          指定教学大纲 MD（可选）
  --head-tpl <path>          指定「教案-模板.docx」
  --week-tpl <path>          指定「课程教学教案-模板.docx」
  --output-dir <dir>         指定输出目录（建议显式指定）
  --font-name <name>         指定字体名称（可选）
  --font-size <size>         指定字体大小（可选）
  --subject <name>           指定科目名称（可选）
  --exe-path <path>          指定 build_word.exe 路径（默认自动定位）

- 内容模式（内联输入，不需预先落盘原始文件）：
  --md-content "<markdown>"
  --json-data-content "<json>"
  --syllabus-content "<markdown>"
说明：封装器会在临时目录写入临时文件，再将路径传给 build_word.exe，底层流程保持一致。

- 其它：
  --timeout <seconds>        子进程超时（默认 600）
  --verbose                  输出详细调试日志到标准错误

五、输出与返回值
- 标准输出始终返回一行 JSON，字段包含但不限于：
  ok, message, files(生成文件路径列表), subject, returncode(底层返回码), elapsed_ms, wrapper_version
- 进程退出码：
  0 成功（ok=true）
  1 未能从底层解析到 JSON（通常底层未按 --stdout-json 输出）
  2 底层返回非 0 且 JSON 表示成功不一致等
  3 超时
  4 未找到 build_word.exe
  5 封装器内部异常

六、常见用法示例
- 自动发现输入：
  .\mcp_wrapper.exe

- 指定输出目录并打印调试日志：
  .\mcp_wrapper.exe --output-dir ".\output" --verbose

- 全路径模式（精准控制输入与模板）：
  .\mcp_wrapper.exe ^
    --md "D:\materials\教案模板标记值-大数据基础.md" ^
    --json-data "D:\materials\大数据基础-data.json" ^
    --syllabus "D:\materials\教学大纲-大数据基础.md" ^
    --head-tpl "D:\templates\教案-模板.docx" ^
    --week-tpl "D:\templates\课程教学教案-模板.docx" ^
    --output-dir "D:\output" --subject "大数据基础" --verbose

- 内联模式（无需在磁盘准备输入文件）：
  .\mcp_wrapper.exe ^
    --md-content "# 课程目标\n..." ^
    --json-data-content "{\"teacher\":\"张三\", \"weeks\": 16}" ^
    --output-dir ".\output"

七、封装器对 build_word.exe 的自动定位规则
- 当封装器为单文件 EXE（frozen）：优先同目录与 .\dist\build_word.exe，其次尝试解包目录（如 sys._MEIPASS）
- 作为脚本运行（开发调试）：还会尝试脚本所在目录及 ../IndependentRunningPackage/dist

反馈建议
如需新增参数（如 --locale/--encoding）、输出更多元数据，或提供 ZIP 包/安装脚本，请联系维护者。