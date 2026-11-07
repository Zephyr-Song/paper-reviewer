"""摘要/结论与正文的数据一致性检查（ABS）。

这条防线针对的是一类反复出现的问题：正文有量化结果，摘要却只写「我们做了评估」，
或者摘要里的数字在正文找不到对应。前者让最强证据不可见，后者是数据不一致。
"""

from __future__ import annotations

import re

from docmodel import Doc
from issues import Issue, truncate

PCT_RE = re.compile(r"(\d+(?:\.\d+)?)\s*\\?%")
RATIO_RE = re.compile(r"\b(\d+)\s*(?:of|/)\s*(\d+)\b")
DIGIT_RE = re.compile(r"\d")

# 结果类信号：出现这些才说明正文有可报的量化结果
RESULT_SIGNAL_RE = re.compile(
    r"\d+(?:\.\d+)?\s*\\?%|\b\d+\s*(?:of|/)\s*\d+\b|p\s*[<=]\s*\.?\d+|"
    r"\bN\s*=\s*\d+|β\s*=|\bSD\s*=",
)


def _numbers(text: str) -> set[str]:
    out = {m.group(1) for m in PCT_RE.finditer(text)}
    for m in RATIO_RE.finditer(text):
        out.add(f"{m.group(1)}/{m.group(2)}")
    return out


def run(doc: Doc, opts: dict) -> list[Issue]:
    issues: list[Issue] = []
    abstract = doc.abstract.strip()
    body = doc.body_text()

    body_signals = RESULT_SIGNAL_RE.findall(body)
    if len(body_signals) < 3:
        return issues  # 正文没有可报结果，摘要不报数也正常

    # ABS-001 摘要完全没有量化结果
    if abstract and not DIGIT_RE.search(abstract):
        issues.append(Issue(
            code="ABS-001", severity="med", title="摘要未包含任何量化结果",
            detail=f"正文有 {len(body_signals)} 处结果性数字（百分比/样本量/比值），"
                   "但摘要里一个数字都没有。摘要的「结果」句是审稿人判断贡献大小的主要依据。",
            evidence=[truncate(b) for b in body_signals[:5]],
            hint="把主结果的数值直接写进摘要，而不是「我们进行了评估」。",
        ))

    # ABS-002 摘要数字在正文找不到
    if abstract:
        abs_nums = _numbers(abstract)
        missing = []
        for n in sorted(abs_nums):
            if "/" in n:
                a, b = n.split("/")
                if not re.search(rf"\b{a}\s*(?:of|/)\s*{b}\b", body):
                    missing.append(n)
            else:
                if not re.search(rf"(?<![\d.]){re.escape(n)}(?![\d])", body):
                    missing.append(n)
        if missing:
            issues.append(Issue(
                code="ABS-002", severity="med", title="摘要中的数字在正文无法对应",
                detail="以下数值只在摘要出现，正文找不到同值。可能是四舍五入不同、"
                       "引用了未报告的数据，或摘要与正文未同步。",
                evidence=[truncate(m) for m in missing[:6]],
                hint="摘要数字必须能追溯到正文的具体图表或段落。",
            ))

    # ABS-003 结论章节没有量化结果
    concl = None
    for key in ("conclusion", "结论", "总结"):
        concl = doc.find_section(key)
        if concl:
            break
    if concl and not DIGIT_RE.search(concl.plain):
        issues.append(Issue(
            code="ABS-003", severity="low", title="结论未呼应量化结果",
            detail=f"结论章节没有任何数字，而正文有 {len(body_signals)} 处结果性数字。"
                   "结论回指一次主结果，能避免「摘要—结论—正文」三处强度不一致。",
        ))

    return issues
