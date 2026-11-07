"""双盲匿名性检查（ANO）。CHI / ACM 采用双盲评审，泄露身份是硬伤。"""

from __future__ import annotations

import re

from docmodel import Doc
from issues import Issue, truncate

EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
IDENTITY_URL_RE = re.compile(
    r"(?:github|gitlab|bitbucket|twitter|x|linkedin|youtube)\.com/[\w.\-]+", re.I
)
HOMEPAGE_RE = re.compile(r"https?://[^\s}\)\]]*~[\w.\-]+", re.I)

SELF_REF = [
    "our previous work", "our prior work", "our earlier work", "our past work",
    "in our earlier study", "we previously published", "our own prior",
    "our previous study", "we have previously", "我们在先前工作", "我们之前的研究",
    "笔者曾", "我们此前",
]

ACK_RE = re.compile(
    r"\\thanks\s*\{|\\acknowledg|acknowledg(?:e)?ments?|致谢|"
    r"funded by|funding|grant\s*(?:no|number|#)|supported by (?:the )?(?:nsf|nih|erc)",
    re.I,
)

# 模板占位符：投稿前必须替换，但和「真实姓名」是两个不同的问题
PLACEHOLDER_RE = re.compile(
    r"\[[^\]]*\]|your name|first author|author name|todo|xxx|待填|姓名",
    re.I,
)
PLACEHOLDER_EMAIL_RE = re.compile(
    r"^(?:you|your|name|author|someone|user|example)@|@example\.(?:com|org)$", re.I
)


def run(doc: Doc, opts: dict) -> list[Issue]:
    issues: list[Issue] = []
    text = doc.plain

    author = (doc.authors or "").strip()
    anonymized = "anonymous" in author.lower() or "匿名" in author
    if author and not anonymized:
        if PLACEHOLDER_RE.search(author):
            issues.append(Issue(
                code="ANO-001", severity="high", title="作者字段仍是占位符",
                detail="作者字段填的是模板占位符（如 [Your Name]），投稿前必须替换为"
                       "匿名署名或真实信息。这是最容易被自己忽略、后果最严重的一类遗漏。",
                evidence=[truncate(author)],
                hint="投稿版填 Anonymous Author(s) / Anonymous Institution，录用版再换回。",
            ))
        else:
            issues.append(Issue(
                code="ANO-001", severity="high", title="作者信息未匿名",
                detail="作者字段包含具体姓名/单位，双盲评审会直接泄露身份。",
                evidence=[truncate(author)],
                hint="投稿版填 Anonymous Author(s) / Anonymous Institution，录用版再换回。",
            ))

    emails = sorted(set(EMAIL_RE.findall(text + "\n" + author)))
    if emails:
        placeholder = all(PLACEHOLDER_EMAIL_RE.search(e) for e in emails)
        issues.append(Issue(
            code="ANO-002", severity="high",
            title="出现占位邮箱" if placeholder else "出现邮箱地址",
            detail=("邮箱仍是模板占位值（如 you@xjtlu.edu.cn），会被评审直接看穿是未完成稿。"
                    if placeholder else "双盲稿件中不应出现任何邮箱。"),
            evidence=[truncate(e) for e in emails[:5]],
        ))

    urls = sorted(set(IDENTITY_URL_RE.findall(text)) | set(HOMEPAGE_RE.findall(text)))
    urls = [u for u in urls if "anonymous" not in u.lower() and "/anon" not in u.lower()]
    if urls:
        issues.append(Issue(
            code="ANO-003", severity="high", title="出现可识别身份的链接",
            detail="代码仓/个人主页链接会暴露作者。匿名评审期应改为匿名镜像。",
            evidence=[truncate(u) for u in urls[:5]],
            hint="用 anonymous.4open.science 之类的匿名仓库替代。",
        ))

    low = text.lower()
    hits = [p for p in SELF_REF if p in low]
    if hits:
        issues.append(Issue(
            code="ANO-004", severity="med", title="自引表述未匿名",
            detail="出现第一人称自引（our previous work 等），等价于署名。",
            evidence=[truncate(h) for h in hits[:5]],
            hint="改为第三人称：「Prior work has shown…」，引用保留但去掉「我们的」。",
        ))

    if ACK_RE.search(doc.raw):
        issues.append(Issue(
            code="ANO-005", severity="med", title="存在致谢/资助信息",
            detail="致谢、\\thanks、资助编号在双盲稿件中通常需要移除或占位。",
            evidence=[truncate(m.group(0)) for m in ACK_RE.finditer(doc.raw)][:3],
        ))

    return issues
