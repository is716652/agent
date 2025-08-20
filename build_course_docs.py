import os
import argparse
import json
from pathlib import Path
from typing import List, Optional

# 复用已有的 OpenAI 封装与部分默认模块（若存在）
from generate_syllabus import call_llm

# 默认模块，可被 --parts 覆盖
DEFAULT_PARTS = [
    "软件测试概论与职业素养",
    "测试需求分析与测试计划",
    "测试用例设计方法",
    "单元测试与缺陷定位",
    "集成测试与系统测试",
    "回归测试与质量度量",
    "自动化测试基础与工具",
    "接口与性能测试入门",
]


def build_syllabus_messages(
    course: str,
    weeks: int,
    parts: Optional[List[str]],
    excludes: Optional[List[str]],
    template_text: str,
    level: str,
    features: Optional[str] = None,
) -> List[dict]:
    parts_text = "\n".join(f"- {i+1}. {m}" for i, m in enumerate(parts or DEFAULT_PARTS))
    exclude_text = "无" if not excludes else ", ".join(excludes)
    include_text = "无" if not features else features.strip()

    system = (
        "你是一名资深职业教育课程负责人，擅长基于岗位能力培养目标设计教学大纲。"
        "请严格按照用户提供的课程信息与模板格式输出内容，语言使用简体中文，表达专业、清晰、可落地。"
    )

    user = f"""
课程名称：{course}
学习者层级/对象：{level}
总周数：{weeks}
大模块（教学部分）：\n{parts_text}
教学大纲的功能说明（不排除项/需重点涵盖的方向）：{include_text}
禁止包含的内容（若出现将扣分并重写）：{exclude_text}

生成要求：
1) 必须严格使用下方模板的结构与标题级别，不得增加或删除字段，不得添加任何额外说明或前后缀；
2) 第1-{weeks}周按周填充：
   - 教学模块：填写本周所属模块名称（模块可跨多周，需形成难度递进与连贯性）；
   - 教学内容：列出3-6个要点（覆盖“知识+技能+实践”）；
   - 重点：1-3条；
   - 难点：1-2条，并给出化解思路（如示例、演示、分层练习等）；
   - 职业技能要求：与岗位能力对应（如会撰写、能执行、能使用工具完成等），可测评、可观察；
   - 教学方法建议：项目化/情境任务/实训/翻转课堂/协作学习/演示讲解/案例分析等；
3) 不得包含“禁止包含的内容”中的条目与表达；并基于“功能说明”优先覆盖和强化应当出现的内容；
4) 特别要求：最后一周安排复习与综合提升，对全课程核心知识点进行回顾、练习与总结；
5) 输出必须完全替换模板中的占位文本，保持 Markdown 列表与标题格式不变；
6) 只输出填充后的模板正文，不要任何多余文字。

模板：
{template_text}
"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def build_plan_messages(
    course: str,
    weeks: int,
    syllabus_md: str,
    data_template_text: str,
) -> List[dict]:
    system = (
        "你是一名一线教研人员，请根据给定的《教学大纲》内容，严格按指定 JSON 模板生成结构化教案数据。"
        "输出必须是严格合法的 JSON，键名与结构必须与模板完全一致。"
    )

    user = f"""
课程名称：{course}
总周数：{weeks}

给定《教学大纲》（Markdown）：
{syllabus_md}

JSON 模板（务必保持相同的键与结构，仅填充具体内容）：
{data_template_text}

生成要求：
1) 严格输出 JSON，不能有 Markdown 代码块标记、注释或多余文本；
2) 字段对应关系：
   - "授课科目" = 课程名称；
   - "总周数" = {weeks}；
   - 对于每周（1..{weeks}）：
     - "课题"：以《教学大纲》中该周的“教学模块”为题；
     - "教学目标"：结合该周“教学内容”和“职业技能要求”，归纳成2-4条目标性表述；
     - "教学重点"：来自该周“重点”；
     - "教学难点"：来自该周“难点”；
     - "授课内容1..4"：从该周“教学内容”中选取最多4条要点（不够则以空字符串补足到4项）；
     - "作业"：结合该周内容与方法给出1项可操作的实践作业（如：编写/执行/设计/分析类任务）；
3) 确保“周次”数组长度为 {weeks}，每项的“周”字段从1顺序递增；
4) 严格保持键名为："授课科目"、"总周数"、"周次"、"周"、"课题"、"教学目标"、"教学重点"、"教学难点"、"授课内容1"、"授课内容2"、"授课内容3"、"授课内容4"、"作业"；
5) 仅输出 JSON 原文。
"""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def ensure_pure_json(text: str) -> str:
    # 去除可能的代码围栏与前后空白
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[-1]
        if "```" in t:
            t = t.rsplit("```", 1)[0]
    # 提取最外层 JSON
    if t and (t[0] != "{" or t[-1] != "}"):
        start = t.find("{")
        end = t.rfind("}")
        if start != -1 and end != -1 and end > start:
            t = t[start : end + 1]
    return t.strip()


def main():
    parser = argparse.ArgumentParser(description="根据四项输入：课程名称/周数/大模块/排除项，生成《课程名称-教学大纲.md》与《课程名称-教案.json》。")
    parser.add_argument("--course", required=True, help="课程名称，例如：软件测试")
    parser.add_argument("--weeks", type=int, default=18, help="总周数，默认18")
    parser.add_argument("--parts", default="", help="以逗号分隔的教学大模块；留空则使用内置建议模块")
    parser.add_argument("--exclude", default="", help="以逗号分隔的禁止包含内容关键词，防止被模型填充")
    parser.add_argument("--features", default="", help="教学大纲的功能说明/需重点涵盖的方向（不排除项），用于引导模型生成")
    parser.add_argument("--level", default="高职学生", help="学习者层级/对象，默认：高职学生")
    parser.add_argument("--template", default=str(Path("templates") / "syllabus_template.md"), help="大纲模板（Markdown）路径")
    parser.add_argument("--json_template", default=str(Path("templates") / "data_template.json"), help="教案 JSON 模板路径")
    parser.add_argument("--model", default="deepseek-chat", help="OpenAI/DeepSeek 模型名，如 deepseek-chat / gpt-4o-mini 等")

    args = parser.parse_args()

    template_path = Path(args.template)
    json_template_path = Path(args.json_template)
    if not template_path.exists():
        raise FileNotFoundError(f"找不到大纲模板文件: {template_path}")
    if not json_template_path.exists():
        raise FileNotFoundError(f"找不到教案 JSON 模板文件: {json_template_path}")

    template_text = template_path.read_text(encoding="utf-8")
    data_template_text = json_template_path.read_text(encoding="utf-8")

    parts = [s.strip() for s in args.parts.split(",") if s.strip()] if args.parts else None
    excludes = [s.strip() for s in args.exclude.split(",") if s.strip()] if args.exclude else None
    features = args.features.strip() if args.features else None

    # 第一阶段：生成教学大纲（Markdown）
    syllabus_messages = build_syllabus_messages(
        course=args.course,
        weeks=args.weeks,
        parts=parts,
        excludes=excludes,
        template_text=template_text,
        level=args.level,
        features=features,
    )
    syllabus_md = call_llm(syllabus_messages, model=args.model)

    out_dir = Path("output")
    out_dir.mkdir(parents=True, exist_ok=True)
    syllabus_path = out_dir / f"{args.course}-教学大纲.md"
    syllabus_path.write_text(syllabus_md, encoding="utf-8")
    print(f"已生成：{syllabus_path}")

    # 第二阶段：根据大纲生成教案 JSON
    plan_messages = build_plan_messages(
        course=args.course,
        weeks=args.weeks,
        syllabus_md=syllabus_md,
        data_template_text=data_template_text,
    )
    plan_json_text = call_llm(plan_messages, model=args.model)
    plan_json_text = ensure_pure_json(plan_json_text)

    try:
        plan_obj = json.loads(plan_json_text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"模型返回的教案 JSON 无法解析：{e}\n原文：\n{plan_json_text[:1000]}")

    # 基础校验
    if plan_obj.get("授课科目") != args.course:
        plan_obj["授课科目"] = args.course
    if plan_obj.get("总周数") != args.weeks:
        plan_obj["总周数"] = args.weeks
    weeks_list = plan_obj.get("周次") or []
    if not isinstance(weeks_list, list) or len(weeks_list) != args.weeks:
        # 若长度不符，简单纠正长度（截断/补齐空项）
        fixed = []
        for i in range(args.weeks):
            item = weeks_list[i] if i < len(weeks_list) else {}
            fixed.append({
                "周": i + 1,
                "课题": item.get("课题", ""),
                "教学目标": item.get("教学目标", ""),
                "教学重点": item.get("教学重点", ""),
                "教学难点": item.get("教学难点", ""),
                "授课内容1": item.get("授课内容1", ""),
                "授课内容2": item.get("授课内容2", ""),
                "授课内容3": item.get("授课内容3", ""),
                "授课内容4": item.get("授课内容4", ""),
                "作业": item.get("作业", ""),
            })
        plan_obj["周次"] = fixed

    plan_path = out_dir / f"{args.course}-{args.weeks}-data.json"
    plan_path.write_text(json.dumps(plan_obj, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"已生成：{plan_path}")


if __name__ == "__main__":
    main()