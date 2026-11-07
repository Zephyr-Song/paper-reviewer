"""papercheck 的回归测试：问题论文要抓得到，规范论文不能误报。

运行：python tests/test_papercheck.py -v
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "papercheck.py"
sys.path.insert(0, str(ROOT / "scripts"))

BAD_TEX = r"""\documentclass{article}
\title{A Study of Things}
\author{Jane Doe \\ Tsinghua University \\ jane@tsinghua.edu.cn}
\begin{document}
\maketitle
\begin{abstract}
We studied things. It was obviously a breakthrough.
\end{abstract}

\section{Introduction}
In our previous work \cite{missing2020} we proved that X always works.
See \url{https://github.com/janedoe/things} for details.
TODO: add the numbers here.

\section{Related Work}
Prior work \cite{known2021} did similar things.

\section{Method}
We recruited N = 30 participants. Later we recruited N = 42 participants.

\section{Results}
The results are clearly perfect.

\section{Conclusion}
Done.

\bibliography{refs}
\end{document}
"""

BAD_BIB = r"""
@article{known2021, title={Known Work}, author={Someone}, year={2021}}
@article{unused2019, title={Unused Work}, author={Nobody}, year={2019}}
@article{known2021, title={Duplicate Key}, author={Dup}, year={2022}}
"""

GOOD_TEX = r"""\documentclass{article}
\title{Effects of Prompting on Reflection: A Controlled Study}
\author{Anonymous Author(s)}
\begin{document}
\maketitle
\begin{abstract}
We investigate whether structured prompting increases ethical reflection among student researchers.
In a controlled study with 30 participants, structured prompting was associated with a 12.4 percent
increase in the number of distinct concerns raised. We report implications for tool design and
discuss three threats to validity.
\end{abstract}

\section{Introduction}
Student researchers often complete ethics reviews as a one-time formality. We ask whether a
conversational interface changes what participants notice. Our contribution is a controlled
comparison of two interface conditions on a shared task set.

\section{Related Work}
Prior work has examined static ethics forms. Recent studies report that checklists reduce the time
spent on review while leaving the range of concerns unchanged \cite{known2021}.

\section{Method}
We recruited 30 participants (N = 30) from two departments. This study was approved by the IRB of
Example University (No. 2026-014). All participants provided written consent before the session.

\section{Results}
Structured prompting was associated with a 12.4 percent increase in distinct concerns, and the
effect held across both departments.

\section{Discussion}
The increase suggests that the interface changes what participants attend to rather than how much
they write. This reading is consistent with prior observations about checklist fatigue.

\section{Limitations}
We note three threats. Construct validity: concern counts proxy for reflection quality, which we did
not measure directly. Internal validity: the two conditions differed in length as well as structure.
External validity: both departments are in the same institution, so generalization is limited.

\section{Conclusion}
Structured prompting appears to broaden the concerns participants raise. Future work should measure
reflection quality directly rather than counting concerns.

\section*{Data availability}
Data is available at osf.io/example after publication.

\section*{Code availability}
Code is available at github.com/anonymous/reflection-study.

\section*{AI use}
Generative AI was not used in this work.

\bibliography{refs}
\end{document}
"""

GOOD_BIB = r"""
@article{known2021, title={Checklists and Review}, author={Prior, A.}, year={2021}}
"""


def _docx(path: Path, paras: list[tuple[int, str]]) -> None:
    ns = 'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"'
    body = ""
    for level, text in paras:
        style = f'<w:pPr><w:pStyle w:val="Heading{level}"/></w:pPr>' if level else ""
        body += f"<w:p>{style}<w:r><w:t>{text}</w:t></w:r></w:p>"
    xml = f'<?xml version="1.0" encoding="UTF-8"?><w:document {ns}><w:body>{body}</w:body></w:document>'
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("[Content_Types].xml", "<Types/>")
        z.writestr("word/document.xml", xml)


class PapercheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, name: str, content: str) -> Path:
        p = self.dir / name
        p.write_text(content, encoding="utf-8")
        return p

    def run_cli(self, *args):
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
        )

    def codes(self, *args) -> set[str]:
        r = self.run_cli(*args, "--format", "json", "--blind")
        self.assertEqual(r.returncode, 0, r.stderr)
        return {i["code"] for i in json.loads(r.stdout)["issues"]}

    # ---------- 检出能力 ----------

    def test_bad_paper_flags_expected_problems(self):
        tex = self.write("bad.tex", BAD_TEX)
        self.write("refs.bib", BAD_BIB)
        codes = self.codes(str(tex))

        expected = {
            "STR-001",   # 缺讨论/局限
            "CIT-001",   # missing2020 不存在
            "CIT-002",   # unused2019 未引用
            "CIT-005",   # known2021 重复
            "ANO-001",   # 作者未匿名
            "ANO-002",   # 邮箱
            "ANO-003",   # github 链接
            "ANO-004",   # our previous work
            "STY-001",   # obviously / always / clearly / perfect
            "STY-005",   # TODO
            "REP-001",   # 有被试无伦理声明
            "REP-005",   # 无 AI 声明
            "REP-006",   # N=30 与 N=42 并存
        }
        missing = expected - codes
        self.assertFalse(missing, f"未检出：{sorted(missing)}；实际：{sorted(codes)}")

    def test_bad_paper_exit_code_with_strict(self):
        tex = self.write("bad.tex", BAD_TEX)
        self.write("refs.bib", BAD_BIB)
        r = self.run_cli(str(tex), "--strict", "--blind")
        self.assertEqual(r.returncode, 1, r.stderr)

    # ---------- 误报控制 ----------

    def test_good_paper_has_no_high_severity(self):
        tex = self.write("good.tex", GOOD_TEX)
        self.write("refs.bib", GOOD_BIB)
        r = self.run_cli(str(tex), "--venue", "chi", "--format", "json", "--blind")
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        high = [i for i in payload["issues"] if i["severity"] == "high"]
        self.assertFalse(high, f"误报严重问题：{[(i['code'], i['title']) for i in high]}")

    def test_anonymous_repo_url_not_flagged(self):
        tex = self.write("good.tex", GOOD_TEX)
        self.write("refs.bib", GOOD_BIB)
        codes = self.codes(str(tex), "--venue", "chi")
        self.assertNotIn("ANO-003", codes)

    # ---------- 开关与口径 ----------

    def test_no_blind_disables_anonymize_checks(self):
        tex = self.write("bad.tex", BAD_TEX)
        self.write("refs.bib", BAD_BIB)
        r = self.run_cli(str(tex), "--format", "json", "--no-blind")
        codes = {i["code"] for i in json.loads(r.stdout)["issues"]}
        self.assertFalse({c for c in codes if c.startswith("ANO-")})

    def test_chi_venue_requires_limitations(self):
        tex = self.write("bad.tex", BAD_TEX)
        self.write("refs.bib", BAD_BIB)
        r = self.run_cli(str(tex), "--venue", "chi", "--format", "json", "--no-blind")
        payload = json.loads(r.stdout)
        issue = next(i for i in payload["issues"] if i["code"] == "STR-001")
        self.assertIn("局限", issue["detail"])

    def test_min_severity_filters(self):
        tex = self.write("bad.tex", BAD_TEX)
        self.write("refs.bib", BAD_BIB)
        r = self.run_cli(str(tex), "--format", "json", "--blind", "--min-severity", "high")
        payload = json.loads(r.stdout)
        self.assertTrue(all(i["severity"] == "high" for i in payload["issues"]))
        self.assertGreater(len(payload["issues"]), 0)

    # ---------- 其他格式 ----------

    def test_markdown_input(self):
        md = self.write("paper.md", """# A Study

## Abstract
We study things with 30 participants.

## Introduction
Text \u3010see\u3011 [@known2021].

## Related Work
Prior work [@known2021].

## Method
We did things.

## Results
Results are shown.

## Discussion
This matters.

## Limitations
Some limits.

## Conclusion
Done.
""")
        self.write("refs.bib", GOOD_BIB)
        r = self.run_cli(str(md), "--venue", "chi", "--format", "json", "--no-blind")
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["stats"]["kind"], "md")

    def test_chinese_headings_satisfy_structure(self):
        md = self.write("cn.md", """# 研究标题

## 摘要
本文研究某问题，共 30 名参与者。

## 引言
背景介绍。

## 相关工作
已有研究 \u3002

## 方法
我们采用问卷法。

## 结果
结果如表格所示。

## 讨论
这说明方法有效。

## 局限
样本量偏小。

## 结论
后续将扩大样本。
""")
        r = self.run_cli(str(md), "--venue", "chi", "--format", "json", "--no-blind")
        codes = {i["code"] for i in json.loads(r.stdout)["issues"]}
        self.assertNotIn("STR-001", codes)

    def test_docx_input(self):
        p = self.dir / "paper.docx"
        _docx(p, [
            (1, "A Study of Things"),
            (2, "Introduction"), (0, "We study things with thirty participants."),
            (2, "Method"), (0, "We ran a study."),
            (2, "Results"), (0, "Results are shown in the table."),
            (2, "Discussion"), (0, "This matters for design."),
            (2, "Conclusion"), (0, "We conclude that it matters."),
        ])
        r = self.run_cli(str(p), "--format", "json", "--no-blind")
        self.assertEqual(r.returncode, 0, r.stderr)
        payload = json.loads(r.stdout)
        self.assertEqual(payload["stats"]["kind"], "docx")
        self.assertGreaterEqual(payload["stats"]["sections"], 5)

    # ---------- 边界 ----------

    def test_missing_file_returns_3(self):
        r = self.run_cli(str(self.dir / "nope.tex"))
        self.assertEqual(r.returncode, 3)
        self.assertIn("找不到文件", r.stderr)
        self.assertNotIn("Traceback", r.stderr)

    def test_out_file_written(self):
        tex = self.write("bad.tex", BAD_TEX)
        self.write("refs.bib", BAD_BIB)
        out = self.dir / "report.md"
        r = self.run_cli(str(tex), "--blind", "-o", str(out))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("# 论文体检报告", out.read_text(encoding="utf-8"))

    def test_list_checks(self):
        r = self.run_cli("--list-checks")
        self.assertEqual(r.returncode, 0)
        self.assertIn("ANO-001", r.stdout)

    # ---------- 摘要一致性 ----------

    def test_abs001_abstract_without_numbers(self):
        tex = self.write("abs1.tex", r"""\documentclass{acmart}
\title{T}
\author{Anonymous Author(s)}
\begin{document}
\begin{abstract}
We study whether a tool helps students. We report a formative evaluation.
\end{abstract}
\section{Introduction}
Text.
\section{Results}
The tool surfaced 20 of 25 issues (80\%) and p < .05 with N = 30 participants.
\section{Conclusion}
It works.
\end{document}
""")
        r = self.run_cli(str(tex), "--format", "json", "--no-blind")
        codes = {i["code"] for i in json.loads(r.stdout)["issues"]}
        self.assertIn("ABS-001", codes)

    def test_abs002_abstract_number_not_in_body(self):
        tex = self.write("abs2.tex", r"""\documentclass{acmart}
\title{T}
\author{Anonymous Author(s)}
\begin{document}
\begin{abstract}
The tool raised overlooked issues by 91.7\% over baseline, with 20 of 25
issues flagged.
\end{abstract}
\section{Introduction}
Text.
\section{Results}
The tool surfaced 20 of 25 issues (80\%) and p < .05 with N = 30 participants.
\section{Conclusion}
It works, 20 of 25 times.
\end{document}
""")
        r = self.run_cli(str(tex), "--format", "json", "--no-blind")
        issues = json.loads(r.stdout)["issues"]
        codes = {i["code"] for i in issues}
        self.assertIn("ABS-002", codes)
        issue = next(i for i in issues if i["code"] == "ABS-002")
        self.assertIn("91.7", " ".join(issue["evidence"]))

    def test_abs_clean_when_consistent(self):
        tex = self.write("abs3.tex", r"""\documentclass{acmart}
\title{T}
\author{Anonymous Author(s)}
\begin{document}
\begin{abstract}
We surface 20 of 25 issues (80\%) that students had not written down, and
p < .05 with N = 30 participants.
\end{abstract}
\section{Introduction}
Text.
\section{Results}
We surfaced 20 of 25 issues (80\%) and p < .05 with N = 30 participants.
\section{Conclusion}
Of 25 issues, 80\% were new to the plan text.
\end{document}
""")
        r = self.run_cli(str(tex), "--format", "json", "--no-blind")
        codes = {i["code"] for i in json.loads(r.stdout)["issues"]}
        self.assertFalse({c for c in codes if c.startswith("ABS-")}, codes)

    # ---------- 真实模板回归 ----------

    def test_inline_thebibliography_is_recognized(self):
        """单文件投稿用 \\begin{thebibliography} + \\bibitem，不该报「未找到文献库」。"""
        tex = self.write("inline.tex", r"""\documentclass{acmart}
\title{T}
\author{Anonymous Author(s)}
\begin{document}
\section{Introduction}
Prior work \citep{known2023} and \citet{other2024} both matter.
\section{Discussion}
We discuss the findings in detail here.
\section{Conclusion}
We conclude.
\begin{thebibliography}{9}
\bibitem[Known(2023)]{known2023} Known. 2023.
\bibitem[Other(2024)]{other2024} Other. 2024.
\end{thebibliography}
\end{document}
""")
        r = self.run_cli(str(tex), "--format", "json", "--no-blind")
        payload = json.loads(r.stdout)
        codes = {i["code"] for i in payload["issues"]}
        self.assertNotIn("CIT-003", codes, payload["issues"])
        self.assertNotIn("CIT-001", codes, payload["issues"])
        self.assertEqual(payload["stats"]["bib_entries"], 2)

    def test_inline_bib_reports_undefined_key(self):
        tex = self.write("inline2.tex", r"""\documentclass{acmart}
\title{T}
\author{Anonymous Author(s)}
\begin{document}
\section{Introduction}
Prior work \citep{ghost2020} is cited.
\section{Discussion}
Text.
\section{Conclusion}
Text.
\begin{thebibliography}{9}
\bibitem[Known(2023)]{known2023} Known. 2023.
\end{thebibliography}
\end{document}
""")
        r = self.run_cli(str(tex), "--format", "json", "--no-blind")
        codes = {i["code"] for i in json.loads(r.stdout)["issues"]}
        self.assertIn("CIT-001", codes)

    def test_title_excludes_thanks_content(self):
        """ACM 模板常见 \\title{...\\thanks{...}}，thanks 不能污染标题。"""
        import docmodel

        tex = self.write("acm.tex", r"""\documentclass[sigconf]{acmart}
\title{SafeBARS Mirror: A Step-by-Step Companion%
\thanks{This is a publicly deployed prototype. No human-subjects study is claimed.}}
\author{[Your Name]}
\affiliation{\institution{XJTLU}\country{China}}
\begin{document}
\begin{abstract}
We present a companion.
\end{abstract}
\section{Introduction}
Text here.
\end{document}
""")
        doc = docmodel.load(tex)
        self.assertEqual(doc.title.strip(), "SafeBARS Mirror: A Step-by-Step Companion")
        self.assertNotIn("publicly deployed prototype", doc.title)
        self.assertIn("[Your Name]", doc.authors)

    def test_placeholder_author_reported_as_placeholder(self):
        tex = self.write("ph.tex", r"""\documentclass{acmart}
\title{T}
\author{[Your Name]}
\begin{document}
\section{Introduction}
Text.
\section{Discussion}
Text.
\section{Conclusion}
Text.
\end{document}
""")
        r = self.run_cli(str(tex), "--format", "json", "--blind")
        payload = json.loads(r.stdout)
        issue = next(i for i in payload["issues"] if i["code"] == "ANO-001")
        self.assertIn("占位符", issue["title"])

    def test_md_report_contains_summary_table(self):
        tex = self.write("bad.tex", BAD_TEX)
        self.write("refs.bib", BAD_BIB)
        r = self.run_cli(str(tex), "--blind")
        self.assertIn("| 类别 | 严重 | 中等 | 提示 |", r.stdout)
        self.assertIn("严重", r.stdout)


if __name__ == "__main__":
    unittest.main(verbosity=2)
