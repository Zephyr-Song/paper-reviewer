"""文风与可读性检查（STY）。以英文写作为主，中文部分只做占位符与术语类检查。"""

from __future__ import annotations

import re

from docmodel import Doc, passive_ratio, word_stats
from issues import Issue, truncate

OVERCLAIM = [
    (r"\bprove[sdn]?\b", "prove"),
    (r"\bobviously\b", "obviously"),
    (r"\bundoubtedly\b", "undoubtedly"),
    (r"\bguarantee[sd]?\b", "guarantee"),
    (r"\bperfect(?:ly)?\b", "perfect"),
    (r"\brevolutionary\b", "revolutionary"),
    (r"\bbreakthrough\b", "breakthrough"),
    (r"\bfirst ever\b", "first ever"),
    (r"\bno one\b", "no one"),
    (r"\beveryone\b", "everyone"),
    (r"\balways\b", "always"),
    (r"\bnever\b", "never"),
]

PLACEHOLDER_RE = re.compile(
    r"\bTODO\b|\bFIXME\b|\bXXX\b|\?\?\?|\[cite\]|\[ref\]|\[待补\]|lorem ipsum|占位",
    re.I,
)

WEASEL_RE = re.compile(
    r"\b(?:some|many|most|various|several|numerous|a lot of|quite|very)\b", re.I
)

VARIANT_PAIRS = [
    ("e-mail", "email"),
    ("data set", "dataset"),
    ("pre-test", "pretest"),
    ("post-test", "posttest"),
    ("web site", "website"),
    ("multi-modal", "multimodal"),
    ("co-design", "codesign"),
    ("real world", "real-world"),
    ("sign up", "sign-up"),
    ("front-end", "frontend"),
    ("back-end", "backend"),
    ("user-name", "username"),
]

TYPOS_RE = re.compile(r"\s{2,}|\s+[,.;:](?=\s)|\.\.(?!\.)")


def run(doc: Doc, opts: dict) -> list[Issue]:
    issues: list[Issue] = []
    body = doc.body_text()
    stats = word_stats(body)
    units = max(stats["units"], 1)

    # STY-001 过度断言
    found: list[str] = []
    for pat, label in OVERCLAIM:
        n = len(re.findall(pat, body, re.I))
        if n:
            found.extend([label] * n)
    if found:
        sev = "med" if len(found) >= 3 else "low"
        issues.append(Issue(
            code="STY-001", severity=sev, title="存在过度断言用词",
            detail=f"共 {len(found)} 处（{'、'.join(sorted(set(found)))}）。"
                   "实证研究宜用 may / suggest / indicate 等限定表达。",
            evidence=[truncate(f) for f in found[:6]],
        ))

    novel = len(re.findall(r"\bnovel\b", body, re.I))
    if novel >= 8:
        issues.append(Issue(
            code="STY-009", severity="low", title="novel 使用过频",
            detail=f"出现 {novel} 次。贡献应靠具体表述支撑，而非反复强调新。",
        ))

    # STY-002 超长句
    long_s = stats["long_sentences"]
    if stats["sentences"] >= 20 and len(long_s) / stats["sentences"] > 0.10:
        issues.append(Issue(
            code="STY-002", severity="med", title="超长句比例偏高",
            detail=f"{len(long_s)}/{stats['sentences']} 句超过 45 词"
                   f"（平均 {stats['mean_sentence']} 词）。拆句可显著提升可读性。",
            evidence=[truncate(s) for s in long_s[:3]],
        ))

    # STY-003 超长段
    long_p = [p for p in re.split(r"\n\s*\n", body)
              if word_stats(p)["units"] > 250]
    if long_p:
        issues.append(Issue(
            code="STY-003", severity="low", title="存在超长段落",
            detail=f"{len(long_p)} 段超过 250 词。一段一个论点。",
            evidence=[truncate(p) for p in long_p[:3]],
        ))

    # STY-004 被动语态
    pr = passive_ratio(body)
    if stats["words"] >= 300 and pr > 0.45:
        issues.append(Issue(
            code="STY-004", severity="low", title="被动语态比例偏高",
            detail=f"约 {pr:.0%} 的句子使用被动语态（学术写作通常 20–35%）。",
            hint="能用主动就主动：「We measured X」优于「X was measured」。",
        ))

    # STY-005 占位符
    ph = PLACEHOLDER_RE.findall(doc.raw)
    if ph:
        issues.append(Issue(
            code="STY-005", severity="med", title="存在未清理的占位符",
            detail=f"{len(ph)} 处 TODO/XXX/[cite] 之类标记。",
            evidence=[truncate(p) for p in sorted(set(ph))[:5]],
        ))

    # STY-006 模糊量词
    weasel = WEASEL_RE.findall(body)
    if len(weasel) >= 15 and len(weasel) / units > 0.008:
        issues.append(Issue(
            code="STY-006", severity="low", title="模糊量词偏多",
            detail=f"{len(weasel)} 处（some/many/most/various…），建议换成具体数量。",
            evidence=[truncate(w) for w in sorted(set(weasel))[:6]],
        ))

    # STY-007 术语不一致
    low = body.lower()
    mixed = [f"{a} / {b}" for a, b in VARIANT_PAIRS if a in low and b in low]
    if mixed:
        issues.append(Issue(
            code="STY-007", severity="low", title="术语写法不一致",
            detail="同一概念出现两种写法，全文应统一。",
            evidence=mixed[:6],
        ))

    # STY-008 排版瑕疵
    typos = TYPOS_RE.findall(doc.raw)
    if len(typos) >= 5:
        issues.append(Issue(
            code="STY-008", severity="low", title="排版细节问题",
            detail=f"{len(typos)} 处多余空格或标点前空格。",
        ))

    return issues
