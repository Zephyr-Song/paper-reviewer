"""引用完整性检查（CIT）。"""

from __future__ import annotations

import re

from docmodel import Doc
from issues import Issue, truncate


def _years(doc: Doc) -> list[int]:
    out = []
    for fields in doc.bib.values():
        m = re.search(r"(19|20)\d{2}", fields.get("year", ""))
        if m:
            out.append(int(m.group(0)))
    return out


def run(doc: Doc, opts: dict) -> list[Issue]:
    issues: list[Issue] = []
    has_bib = bool(doc.bib)

    if doc.kind == "tex" and not doc.bib_paths:
        issues.append(Issue(
            code="CIT-003", severity="med", title="未找到 .bib 文件",
            detail="源文件里没有 \\bibliography{} / \\addbibresource{}，目录下也没有 .bib。"
                   "引用无法核对，跳过条目级检查。",
            hint="用 --bib 显式指定文献库路径。",
        ))
    elif doc.kind == "tex" and doc.bib_paths and not has_bib:
        issues.append(Issue(
            code="CIT-003", severity="high", title="文献库为空或解析失败",
            detail=f"找到 {len(doc.bib_paths)} 个 .bib 但解析出 0 条条目，可能编码或格式异常。",
            evidence=[str(p.name) for p in doc.bib_paths],
        ))

    if has_bib:
        undefined = sorted(set(doc.cites) - set(doc.bib))
        if undefined:
            issues.append(Issue(
                code="CIT-001", severity="high", title="正文引用了不存在的文献",
                detail=f"{len(undefined)} 个引用键在 .bib 中找不到，编译会出 [?]。",
                evidence=[truncate(u) for u in undefined[:8]],
                hint="补条目或删引用；拼写错（如 author2020 vs authors2020）是常见原因。",
            ))

        unused = sorted(set(doc.bib) - set(doc.cites))
        if unused:
            issues.append(Issue(
                code="CIT-002", severity="low", title="存在未被引用的文献条目",
                detail=f"{len(unused)} 条 bib 条目正文从未引用（多数会议要求参考文献与正文一一对应）。",
                evidence=[truncate(u) for u in unused[:8]],
            ))

        if doc.bib_duplicates:
            issues.append(Issue(
                code="CIT-005", severity="high", title="文献库存在重复键",
                detail="同一键出现多次，后一条会静默覆盖前一条，导致引用内容错乱。",
                evidence=[truncate(k) for k in doc.bib_duplicates[:8]],
            ))

        years = _years(doc)
        if len(years) >= 10:
            newest = max(years)
            recent = sum(1 for y in years if newest - y <= 5) / len(years)
            if recent < 0.30:
                issues.append(Issue(
                    code="CIT-006", severity="low", title="近五年文献占比偏低",
                    detail=f"仅 {recent:.0%} 条目发表于最近五年（以库内最新年份 {newest} 为基准）。",
                    hint="相关工作若只引经典不看近期，容易被判「不了解最新进展」。",
                ))

    if not doc.cites:
        issues.append(Issue(
            code="CIT-004", severity="med", title="未检测到正文引用",
            detail="全文没有识别到引用标记。若确为立场/短文可忽略；研究论文通常不正常。",
            hint="Markdown 用 [@key]，LaTeX 用 \\cite{key}。",
        ))

    return issues
