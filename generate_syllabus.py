import os
import argparse
from pathlib import Path
from typing import List, Optional

try:
    from openai import OpenAI
except ImportError:
    OpenAI = None  # type: ignore


DEFAULT_MODULES = [
    "软件测试概论与职业素养",
    "测试需求分析与测试计划",
    "测试用例设计方法",
    "单元测试与缺陷定位",
    "集成测试与系统测试",
    "回归测试与质量度量",
    "自动化测试基础与工具",
    "接口与性能测试入门",
]


def build_prompt(course: str, weeks: int, level: str, modules: Optional[List[str]], template_text: str) -> List[dict]:
    modules_text = "\n".join(f"- {i+1}. {m}" for i, m in enumerate(modules or DEFAULT_MODULES))

    system = (
        "你是一名资深职业教育课程负责人，擅长基于岗位能力培养目标设计18周教学大纲。"
        "请严格按照用户提供的课程信息与模板格式输出内容，语言使用简体中文，表达专业、清晰、可落地。"
    )

    user = f"""
课程名称：{course}
开课对象：{level}
总周数：{weeks}
建议教学模块：\n{modules_text}

要求：
1) 必须严格使用下方模板的结构与标题级别，不得增加或删除字段，不得添加额外说明或前后缀；
2) 第1-18周按周填充：
   - 教学模块：填写本周所属的模块名称（模块可跨多周，需在周次之间形成梯度与连贯性）；
   - 教学内容：列出3-6个可操作要点（尽量涵盖“知识+技能+实践”）；
   - 重点：1-3条；
   - 难点：1-2条，并给出化解思路（如示例、演示、分层练习等）；
   - 职业技能要求：与岗位能力对应，描述应可测评、可观察（如会撰写、能执行、能使用工具完成等）；
   - 教学方法建议：结合项目化/情境任务/实训/翻转课堂/协作学习/演示讲解/案例分析等；
3) 需体现从基础到进阶的难度递进；覆盖手工测试、用例设计、缺陷管理、自动化与接口/性能等核心能力；
4) 输出必须完全替换模板中的占位文本，保持 Markdown 列表与标题格式不变；
5) 只输出填充后的模板正文，不要任何多余文字。

模板：
{template_text}
"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def render_output_path(course: str, output: Optional[str]) -> Path:
    if output:
        return Path(output)
    safe_name = "".join(ch for ch in course if ch.isalnum() or ch in ("_", "-")) or "syllabus"
    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir / f"syllabus_{safe_name}.md"


def call_llm(messages: List[dict], model: str) -> str:
    if OpenAI is None:
        raise RuntimeError("未安装 openai 库。请先运行: pip install -r requirements.txt")

    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("未检测到 OPENAI_API_KEY 或 DEEPSEEK_API_KEY 环境变量，请先配置 API Key。")

    base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL")
    if not base_url and os.getenv("DEEPSEEK_API_KEY"):
        base_url = "https://api.deepseek.com"

    client = OpenAI(api_key=api_key, base_url=base_url) if base_url else OpenAI(api_key=api_key)
    resp = client.chat.completions.create(
        model=model,
        temperature=0.7,
        messages=messages,
    )
    content = resp.choices[0].message.content if resp.choices else ""
    if not content:
        raise RuntimeError("模型未返回内容，请稍后重试或调整提示词。")
    return content


def main():
    parser = argparse.ArgumentParser(description="根据模板与课程信息，调用大模型生成18周教学大纲并输出为Markdown。")
    parser.add_argument("--course", required=True, help="课程名称，例如：软件测试")
    parser.add_argument("--weeks", type=int, default=18, help="总周数，默认18")
    parser.add_argument("--level", default="高职学生", help="学习者层级/对象，默认：高职学生")
    parser.add_argument(
        "--modules",
        default="",
        help="以逗号分隔的模块清单；留空则使用内置建议模块",
    )
    parser.add_argument(
        "--template",
        default=str(Path("templates") / "syllabus_template.md"),
        help="模板文件路径（Markdown）",
    )
    parser.add_argument(
        "--model", default="deepseek-chat", help="OpenAI/DeepSeek 模型名，如 deepseek-chat / gpt-4o-mini 等"
    )
    parser.add_argument(
        "--output", default="", help="输出Markdown文件路径，缺省为 output/syllabus_<课程名>.md"
    )

    args = parser.parse_args()

    template_path = Path(args.template)
    if not template_path.exists():
        raise FileNotFoundError(f"找不到模板文件: {template_path}")

    template_text = template_path.read_text(encoding="utf-8")
    modules = [m.strip() for m in args.modules.split(",") if m.strip()] if args.modules else None

    messages = build_prompt(
        course=args.course,
        weeks=args.weeks,
        level=args.level,
        modules=modules,
        template_text=template_text,
    )

    content = call_llm(messages, model=args.model)

    out_path = render_output_path(args.course, args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(content, encoding="utf-8")

    print(f"已生成教学大纲: {out_path}")


if __name__ == "__main__":
    main()