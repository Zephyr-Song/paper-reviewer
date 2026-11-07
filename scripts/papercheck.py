#!/usr/bin/env python3
"""papercheck —— 学术论文体检：结构、引用、匿名、文风、报告规范。

用法：
    python papercheck.py paper.tex
    python papercheck.py paper.tex --venue chi --blind
    python papercheck.py thesis.docx --format json --out report.json
    python papercheck.py paper.tex --min-severity med --strict

退出码：0 正常；1 --strict 且存在严重问题；3 文件解析失败。
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import checks_anonymize  # noqa: E402
import checks_citation  # noqa: E402
import checks_reporting  # noqa: E402
import checks_structure  # noqa: E402
import checks_style  # noqa: E402
import docmodel  # noqa: E402
from issues import (  # noqa: E402
    CATEGORY_LABEL,
    SEVERITY_LABEL,
    SEVERITY_MARK,
    SEVERITY_ORDER,
    Issue,
)

VERSION = "1.0.0"

MODULES = [
    ("STR", checks_structure),
    ("CIT", checks_citation),
    ("ANO", checks_anonymize),
    ("STY", checks_style),
    ("REP", checks_reporting),
]

CHECK_INDEX = [
    ("STR-001", "缺少必需章节"), ("STR-002", "过短/空章节"), ("STR-003", "讨论/局限篇幅偏薄"),
    ("STR-004", "缺少摘要"), ("STR-005", "未识别到标题"), ("STR-006", "章节层级跳跃"),
    ("CIT-001", "引用了不存在的文献"), ("CIT-002", "存在未引用条目"), ("CIT-003", "未找到文献库"),
    ("CIT-004", "未检测到正文引用"), ("CIT-005", "文献库重复键"), ("CIT-006", "近五年文献占比偏低"),
    ("ANO-001", "作者信息未匿名"), ("ANO-002", "出现邮箱"), ("ANO-003", "出现可识别链接"),
    ("ANO-004", "自引表述未匿名"), ("ANO-005", "存在致谢/资助信息"),
    ("STY-001", "过度断言"), ("STY-002", "超长句"), ("STY-003", "超长段落"),
    ("STY-004", "被动语态偏高"), ("STY-005", "未清理占位符"), ("STY-006", "模糊量词偏多"),
    ("STY-007", "术语写法不一致"), ("STY-008", "排版细节问题"), ("STY-009", "novel 使用过频"),
    ("REP-001", "缺少伦理/IRB 声明"), ("REP-002", "缺少知情同意"), ("REP-003", "缺少数据可用性"),
    ("REP-004", "缺少代码可用性"), ("REP-005", "缺少生成式 AI 声明"),
    ("REP-006", "样本量表述不一致"), ("REP-007", "局限讨论过于简略"),
]


def log(msg: str) -> None:
    print(f"[papercheck] {msg}", file=sys.stderr, flush=True)


def collect(doc, opts: dict) -> list[Issue]:
    issues: list[Issue] = []
    for name, module in MODULES:
        if name == "ANO" and not opts.get("blind"):
            continue
        try:
            issues.extend(module.run(doc, opts))
        except Exception as e:  # 单个检查崩掉不应拖垮整份报告
            log(f"检查模块 {name} 异常：{e}")
    issues.sort(key=lambda i: (SEVERITY_ORDER[i.severity], i.code))
    return issues


def doc_stats(doc) -> dict:
    body = doc.body_text()
    stats = docmodel.word_stats(body)
    return {
        "kind": doc.kind,
        "title": doc.title,
        "sections": len(doc.sections),
        "words": stats["words"],
        "cjk": stats["cjk"],
        "sentences": stats["sentences"],
        "mean_sentence": stats["mean_sentence"],
        "citations_in_text": sum(doc.cites.values()),
        "citation_keys": len(doc.cites),
        "bib_entries": len(doc.bib),
        "bib_files": [str(p) for p in doc.bib_paths],
        "figures": doc.figures,
        "tables": doc.tables,
        "labels": len(doc.labels),
    }


def render_md(doc, issues: list[Issue], opts: dict) -> str:
    stats = doc_stats(doc)
    counts = Counter(i.severity for i in issues)
    out: list[str] = []

    out.append("# 论文体检报告\n")
    out.append(f"- 文件：`{doc.path.name}`（{stats['kind']}）")
    if stats["title"]:
        out.append(f"- 标题：{stats['title']}")
    out.append(
        f"- 正文：{stats['sections']} 节 · 英文 {stats['words']} 词 · 中文 {stats['cjk']} 字 · "
        f"平均句长 {stats['mean_sentence']} 词"
    )
    out.append(
        f"- 引用：正文 {stats['citations_in_text']} 处 / {stats['citation_keys']} 个键 · "
        f"文献库 {stats['bib_entries']} 条"
    )
    out.append(f"- 图表：{stats['figures']} 图 · {stats['tables']} 表")
    out.append(f"- 评审口径：venue={opts['venue']} · 双盲={'是' if opts['blind'] else '否'}\n")

    if not issues:
        out.append("## 结论\n\n未发现问题。建议再人工核对：贡献表述、图表可读性、结果与结论的一致性。\n")
        return "\n".join(out)

    out.append(
        f"**严重 {counts.get('high', 0)} · 中等 {counts.get('med', 0)} · "
        f"提示 {counts.get('low', 0)}**\n"
    )

    by_cat: dict[str, Counter] = {}
    for i in issues:
        by_cat.setdefault(i.category, Counter())[i.severity] += 1
    out.append("| 类别 | 严重 | 中等 | 提示 |")
    out.append("| --- | --- | --- | --- |")
    for cat in ("STR", "CIT", "ANO", "STY", "REP"):
        if cat in by_cat:
            c = by_cat[cat]
            out.append(f"| {CATEGORY_LABEL[cat]} | {c.get('high', 0)} | {c.get('med', 0)} | {c.get('low', 0)} |")
    out.append("")

    for sev in ("high", "med", "low"):
        group = [i for i in issues if i.severity == sev]
        if not group:
            continue
        out.append(f"## {SEVERITY_MARK[sev]} {SEVERITY_LABEL[sev]}（{len(group)}）\n")
        for i in group:
            out.append(f"### [{i.code}] {i.title}\n")
            out.append(i.detail)
            if i.evidence:
                out.append("")
                for e in i.evidence:
                    out.append(f"- `{e}`")
            if i.hint:
                out.append("")
                out.append(f"> {i.hint}")
            out.append("")

    return "\n".join(out).rstrip() + "\n"


def main(argv: list[str]) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            if (stream.encoding or "").lower() not in ("utf-8", "utf8"):
                stream.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    ap = argparse.ArgumentParser(
        prog="papercheck",
        description="学术论文体检：结构 / 引用 / 双盲匿名 / 文风 / 报告规范。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="退出码：0 正常，1 --strict 且存在严重问题，3 解析失败。",
    )
    ap.add_argument("path", nargs="?", help="论文文件（.tex / .md / .docx / .txt）")
    ap.add_argument("--bib", help="显式指定 .bib 文献库（LaTeX 通常可自动发现）")
    ap.add_argument("--venue", default="generic",
                    choices=["generic", "chi", "acm", "neurips", "thesis"],
                    help="评审口径，决定必需章节集合，默认 generic")
    ap.add_argument("--blind", dest="blind", action="store_true", default=None,
                    help="强制启用双盲匿名检查")
    ap.add_argument("--no-blind", dest="blind", action="store_false",
                    help="关闭双盲匿名检查")
    ap.add_argument("--min-severity", default="low", choices=["high", "med", "low"],
                    help="报告里保留的最低级别，默认 low")
    ap.add_argument("--format", default="md", choices=["md", "json"])
    ap.add_argument("-o", "--out", help="写入文件（默认打印到 stdout）")
    ap.add_argument("--strict", action="store_true", help="存在严重问题时返回退出码 1")
    ap.add_argument("--list-checks", action="store_true", help="列出全部检查项")
    ap.add_argument("-V", "--version", action="version", version=f"%(prog)s {VERSION}")

    args = ap.parse_args(argv)

    if args.list_checks:
        print("检查项：\n")
        for code, title in CHECK_INDEX:
            print(f"  {code:<8} {CATEGORY_LABEL[code.split('-')[0]]}  {title}")
        return 0

    if not args.path:
        ap.print_help()
        return 2

    blind = args.blind if args.blind is not None else args.venue in ("chi", "acm")
    opts = {"venue": args.venue, "blind": blind}

    try:
        doc = docmodel.load(args.path)
    except (FileNotFoundError, ValueError) as e:
        log(str(e))
        return 3
    except Exception as e:
        log(f"解析失败：{e}")
        return 3

    if args.bib:
        bp = Path(args.bib).expanduser()
        if not bp.is_file():
            log(f"找不到 .bib：{bp}")
            return 3
        entries, dups = docmodel.parse_bib(bp)
        doc.bib.update(entries)
        doc.bib_duplicates.extend(dups)
        doc.bib_paths.append(bp)

    issues = collect(doc, opts)
    floor = SEVERITY_ORDER[args.min_severity]
    issues = [i for i in issues if SEVERITY_ORDER[i.severity] <= floor]

    if args.format == "json":
        payload = {
            "version": VERSION,
            "file": str(doc.path),
            "stats": doc_stats(doc),
            "venue": args.venue,
            "blind": blind,
            "counts": dict(Counter(i.severity for i in issues)),
            "issues": [i.as_dict() for i in issues],
        }
        text = json.dumps(payload, ensure_ascii=False, indent=2)
    else:
        text = render_md(doc, issues, opts)

    if args.out:
        Path(args.out).expanduser().write_text(text, encoding="utf-8")
        log(f"已写入 {args.out}")
    else:
        print(text)

    if args.strict and any(i.severity == "high" for i in issues):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
