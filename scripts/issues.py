"""检查项的数据结构。"""

from __future__ import annotations

from dataclasses import dataclass, field

SEVERITY_ORDER = {"high": 0, "med": 1, "low": 2}
SEVERITY_LABEL = {"high": "严重", "med": "中等", "low": "提示"}
SEVERITY_MARK = {"high": "🔴", "med": "🟡", "low": "⚪"}

CATEGORY_LABEL = {
    "STR": "结构",
    "CIT": "引用",
    "ANO": "匿名",
    "STY": "文风",
    "REP": "报告规范",
}


@dataclass
class Issue:
    code: str
    severity: str
    title: str
    detail: str
    evidence: list[str] = field(default_factory=list)
    hint: str = ""

    @property
    def category(self) -> str:
        return self.code.split("-")[0]

    def as_dict(self) -> dict:
        return {
            "code": self.code,
            "severity": self.severity,
            "category": self.category,
            "title": self.title,
            "detail": self.detail,
            "hint": self.hint,
            "evidence": self.evidence,
        }


def truncate(s: str, limit: int = 140) -> str:
    s = " ".join(s.split())
    return s if len(s) <= limit else s[: limit - 1] + "…"
