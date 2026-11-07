"""报告规范检查（REP）：伦理、同意、数据/代码可用性、生成式 AI 声明、样本量一致性。"""

from __future__ import annotations

import re

from docmodel import Doc, word_stats
from issues import Issue, truncate

PARTICIPANT_RE = re.compile(
    r"\bparticipants?\b|\bsubjects?\b|\buser study\b|\binterview(?:s|ed)?\b|"
    r"\bsurvey(?:s|ed)?\b|被试|参与者|用户研究|访谈",
    re.I,
)
ETHICS_RE = re.compile(
    r"\bethic(?:s|al)?\b|\birb\b|institutional review|review board|"
    r"伦理|审查委员会|知情同意书",
    re.I,
)
CONSENT_RE = re.compile(r"\bconsent\b|知情同意", re.I)
DATA_RE = re.compile(
    r"data availability|"
    r"data (?:are|is) (?:publicly |openly |freely )?(?:available|released|shared)|"
    r"(?:datasets?|data) (?:can be|may be|are) (?:obtained|requested|downloaded|accessed)|"
    r"available (?:at|from|via) (?:https?://|osf\.io|zenodo|figshare|doi)|"
    r"osf\.io|zenodo\.org|figshare\.com|"
    r"公开数据集|数据可用|数据已公开|数据可向",
    re.I,
)
CODE_RE = re.compile(
    r"(?:code|implementation|artifact|artifacts|materials?) "
    r"(?:is |are |was )?(?:publicly |openly )?(?:available|released|shared)|"
    r"available (?:at|from|via) https?://(?:www\.)?(?:github|gitlab|zenodo|figshare)|"
    r"github\.com/[\w.-]+/[\w.-]+|"
    r"代码(?:已)?公开|代码可从|开源实现",
    re.I,
)
AI_DISCLOSE_RE = re.compile(
    r"generative ai|ai[- ]assist|\bgenai\b|chatgpt (?:was )?used|used (?:chatgpt|gpt|llm)|"
    r"language model (?:was|were) used|llm (?:was|were) used|"
    r"(?:writ|edit|draft|paraphras)\w*[^.]{0,60}(?:chatgpt|llm|generative)|"
    r"生成式|ai\s*辅助|人工智能辅助",
    re.I,
)
N_RE = re.compile(r"\b[Nn]\s*=\s*(\d{1,5})\b")


def run(doc: Doc, opts: dict) -> list[Issue]:
    issues: list[Issue] = []
    body = doc.body_text()
    full = doc.plain
    venue = opts.get("venue", "generic")

    has_participants = bool(PARTICIPANT_RE.search(body))

    if has_participants and not ETHICS_RE.search(full):
        issues.append(Issue(
            code="REP-001", severity="med", title="缺少伦理/IRB 声明",
            detail="正文涉及人类被试，但未找到伦理审查或 IRB 相关表述。",
            hint="加一句：This study was approved by the <IRB> of <Institution> (No. xxx).",
        ))

    if has_participants and not CONSENT_RE.search(full):
        issues.append(Issue(
            code="REP-002", severity="low", title="缺少知情同意表述",
            detail="未提及参与者知情同意。",
        ))

    if not DATA_RE.search(full):
        issues.append(Issue(
            code="REP-003", severity="low", title="缺少数据可用性声明",
            detail="未找到数据可用性表述。越来越多会议要求明确数据获取方式。",
            hint="即使不公开，也应写明「因隐私原因不可公开，可向作者申请」。",
        ))

    if not CODE_RE.search(full):
        issues.append(Issue(
            code="REP-004", severity="low", title="缺少代码/材料可用性声明",
            detail="未找到代码或材料获取方式。",
        ))

    if not AI_DISCLOSE_RE.search(full):
        # 生成式 AI 披露是 ACM/CHI 的硬性要求；其它会议口径只是趋势，降级为提示，
        # 避免对着 IEEE 稿子说「ACM/CHI 要求…」这种张冠李戴的断言。
        if venue in ("acm", "chi"):
            issues.append(Issue(
                code="REP-005", severity="med", title="缺少生成式 AI 使用声明",
                detail="ACM/CHI 要求披露生成式 AI 在写作或分析中的使用情况；未检测到相关表述。",
                hint="未使用也应显式声明「Generative AI was not used」，比沉默更安全。",
            ))
        else:
            issues.append(Issue(
                code="REP-005", severity="low", title="未声明生成式 AI 使用情况",
                detail=f"按 venue={venue} 口径不强制，但越来越多会议要求披露；本文未检测到相关表述。",
                hint="可加一句「Generative AI was not used」或说明具体用途，成本很低。",
            ))

    values = sorted({int(v) for v in N_RE.findall(full)})
    if len(values) > 1:
        issues.append(Issue(
            code="REP-006", severity="low", title="样本量表述不一致",
            detail=f"正文出现多个 N 值：{', '.join(map(str, values))}。"
                   "若是不同研究阶段请注明，否则需统一。",
            evidence=[truncate(m.group(0)) for m in list(N_RE.finditer(full))[:8]],
        ))

    lim = doc.find_section("limitation", "threats to validity", "局限", "不足")
    if lim and word_stats(lim.plain)["units"] < 60:
        issues.append(Issue(
            code="REP-007", severity="low", title="局限讨论过于简略",
            detail=f"局限章节仅约 {word_stats(lim.plain)['units']} 词，通常不足以覆盖效度威胁。",
            hint="按 construct / internal / external validity 三段式各写 2–3 句。",
        ))

    return issues
