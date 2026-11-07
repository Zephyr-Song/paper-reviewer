"""结构与完整性检查（STR）。"""

from __future__ import annotations

from docmodel import Doc, word_stats
from issues import Issue, truncate

ALIASES: dict[str, list[str]] = {
    "abstract": ["abstract", "摘要"],
    "introduction": ["introduction", "引言", "介绍", "background and motivation"],
    "related": ["related work", "related works", "literature review", "prior work",
                "相关工作", "文献综述", "研究背景"],
    "method": ["method", "methodology", "approach", "study design", "system design",
               "materials and methods", "方法", "研究设计", "方案", "实验设计"],
    "results": ["result", "results", "finding", "findings", "evaluation", "experiment",
                "结果", "发现", "评估", "实验", "数据分析"],
    "discussion": ["discussion", "讨论"],
    "limitations": ["limitation", "limitations", "threats to validity", "局限", "不足", "研究局限"],
    "conclusion": ["conclusion", "conclusions", "结论", "总结", "future work", "未来工作"],
}

DISPLAY = {
    "abstract": "摘要", "introduction": "引言", "related": "相关工作", "method": "方法",
    "results": "结果", "discussion": "讨论", "limitations": "局限", "conclusion": "结论",
}

REQUIRED: dict[str, list[str]] = {
    "generic": ["introduction", "method", "results", "discussion", "conclusion"],
    "chi": ["introduction", "related", "method", "results", "discussion",
            "limitations", "conclusion"],
    "acm": ["introduction", "related", "method", "results", "discussion",
            "limitations", "conclusion"],
    "neurips": ["introduction", "related", "method", "results", "discussion", "conclusion"],
    "ieee": ["introduction", "related", "method", "results", "discussion", "conclusion"],
    "thesis": ["introduction", "related", "method", "results", "discussion",
               "limitations", "conclusion"],
}

SKIP_EMPTY = ("reference", "bibliograph", "参考文献", "致谢", "acknowledg", "appendix", "附录")


def run(doc: Doc, opts: dict) -> list[Issue]:
    issues: list[Issue] = []

    # 没有章节结构时（PDF 表单、无标题的纯文本），结构类检查全部无意义，
    # 直接命中会制造大量噪声，改为给一条说明。
    if not doc.sections:
        issues.append(Issue(
            code="STR-007", severity="low", title="未识别到章节结构",
            detail="这份文件没有可识别的标题层级（常见于 PDF 表单、扫描件或未使用标题的文件），"
                   "结构类检查（必需章节、空章节、层级跳跃）已跳过；引用与文风类检查仍然有效。",
            hint="若这是论文稿，请改用带 \\section 或 Markdown 标题的版本，结构检查才有意义。",
        ))
        return issues

    venue = opts.get("venue", "generic")
    required = REQUIRED.get(venue, REQUIRED["generic"])
    titles_lower = [s.title.lower() for s in doc.sections]

    def has(key: str) -> bool:
        return any(a in t for a in ALIASES[key] for t in titles_lower)

    # 摘要单独判断：它常常不是 \section，而是 abstract 环境或首段
    if not doc.abstract.strip() and not has("abstract"):
        issues.append(Issue(
            code="STR-004", severity="high", title="缺少摘要",
            detail="没有识别到摘要（\\begin{abstract}、Abstract 章节或首个摘要段）。",
            hint="摘要应在一段内交代：问题、做法、关键结果（含量级）、意义。",
        ))

    missing = [DISPLAY[k] for k in required if not has(k)]
    if missing:
        issues.append(Issue(
            code="STR-001", severity="high", title="缺少必需章节",
            detail=f"按 {venue} 惯例缺少：{'、'.join(missing)}。若标题命名不同，可忽略此项。",
            evidence=[f"现有章节：{', '.join(doc.section_titles()[:12])}"],
            hint="章节标题尽量用惯例命名，审稿人按图索骥找不到会直接扣分。",
        ))

    if not doc.title.strip():
        issues.append(Issue(
            code="STR-005", severity="med", title="未识别到标题",
            detail="\\title{} 或一级标题为空，无法核对标题与摘要/结论的一致性。",
        ))

    # 只看顶层章节：二阶小标题（如 "Participants"）本来就该短，检查它会大量误报
    top_level = min((s.level for s in doc.sections), default=1)
    empty = []
    for s in doc.sections:
        if any(k in s.key for k in SKIP_EMPTY):
            continue
        if s.level == top_level and word_stats(s.plain)["units"] < 20:
            empty.append(s.title)
    if empty:
        issues.append(Issue(
            code="STR-002", severity="med", title="存在过短/空章节",
            detail="以下章节内容不足 20 个词元，可能忘记填充或标题误用。",
            evidence=[truncate(t) for t in empty],
        ))

    stats = word_stats(doc.body_text())
    total = max(stats["units"], 1)
    thin = []
    for key in ("discussion", "limitations"):
        sec = doc.find_section(*ALIASES[key])
        if not sec:
            continue
        share = word_stats(sec.plain)["units"] / total
        if share < 0.03:
            thin.append(f"{sec.title}（{share:.1%}）")
    if thin:
        issues.append(Issue(
            code="STR-003", severity="low", title="讨论/局限篇幅偏薄",
            detail="占正文比例低于 3%。审稿人通常把这类章节视为「只报结果不解释」。",
            evidence=thin,
            hint="讨论要回答「为什么是这个结果」，局限要写清对结论有效性的影响。",
        ))

    jumps = []
    prev = 0
    for s in doc.sections:
        if prev and s.level > prev + 1:
            jumps.append(f"{s.title}（层级 {prev} → {s.level}）")
        prev = s.level
    if jumps:
        issues.append(Issue(
            code="STR-006", severity="low", title="章节层级跳跃",
            detail="出现跨级标题（如一级下面直接三级）。",
            evidence=[truncate(j) for j in jumps[:5]],
        ))

    return issues
