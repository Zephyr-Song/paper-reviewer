"""统一文档模型：把 .tex / .md / .docx / .txt 解析成可检查的结构。

只依赖标准库。目标不是完整解析 LaTeX，而是拿到足够做体检的骨架：
章节、正文、引用键、bib 条目、图表数量、标签与引用关系。
"""

from __future__ import annotations

import html as htmllib
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

TEX_EXTS = {".tex", ".ltx"}
MD_EXTS = {".md", ".markdown", ".txt"}

_SEC_LEVEL = {"section": 1, "subsection": 2, "subsubsection": 3, "paragraph": 4}
_SEC_RE = re.compile(
    r"\\(?P<cmd>section|subsection|subsubsection|paragraph)\*?\s*(?:\[[^\]]*\])?\s*"
    r"\{(?P<title>(?:[^{}]|\{[^{}]*\})*)\}"
)

_CITE_CMDS = (
    "cite|citep|citet|citealp|citealt|citeauthor|citeyear|parencite|"
    "textcite|autocite|footcite|supercite"
)
_CITE_RE = re.compile(r"\\(" + _CITE_CMDS + r")\*?\s*(?:\[[^\]]*\]\s*){0,2}\{([^}]*)\}")
_LABEL_RE = re.compile(r"\\label\{([^}]*)\}")
_REF_RE = re.compile(r"\\(?:ref|autoref|cref|Cref|eqref|pageref|nameref)\{([^}]*)\}")
_BIBFILE_RE = re.compile(r"\\(?:bibliography|addbibresource)\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
_THEBIB_RE = re.compile(
    r"\\begin\{thebibliography\}(?:\{[^}]*\})?(.*?)\\end\{thebibliography\}", re.S
)
_BIBITEM_RE = re.compile(r"\\bibitem(?:\[([^\]]*)\])?\s*\{([^}]*)\}")
_TITLE_RE = re.compile(r"\\title\s*(?:\[[^\]]*\])?\s*\{", re.I)
_AUTHOR_RE = re.compile(r"\\author\s*(?:\[[^\]]*\])?\s*\{", re.I)
_ABSTRACT_RE = re.compile(r"\\begin\{abstract\}(.*?)\\end\{abstract\}", re.S | re.I)

_MD_HEAD_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")
_MD_CITE_RE = re.compile(r"\[@([^\];,\s]+)")

_BIB_ENTRY_RE = re.compile(r"@(\w+)\s*\{\s*([^,\s]+)\s*,", re.I)
_BIB_FIELD_RE = re.compile(
    r"(\w+)\s*=\s*(\{(?:[^{}]|\{[^{}]*\})*\}|\"[^\"]*\"|[^,\n]+)", re.I
)


@dataclass
class Section:
    level: int
    title: str
    raw: str
    plain: str
    index: int

    @property
    def key(self) -> str:
        return self.title.strip().lower()


@dataclass
class Doc:
    path: Path
    kind: str
    raw: str
    plain: str
    sections: list[Section] = field(default_factory=list)
    cites: Counter = field(default_factory=Counter)
    bib: dict[str, dict] = field(default_factory=dict)
    bib_paths: list[Path] = field(default_factory=list)
    bib_duplicates: list[str] = field(default_factory=list)
    labels: set[str] = field(default_factory=set)
    refs: list[str] = field(default_factory=list)
    figures: int = 0
    tables: int = 0
    title: str = ""
    authors: str = ""
    abstract: str = ""

    # ---- 便捷访问 ----

    def section_titles(self) -> list[str]:
        return [s.title for s in self.sections]

    def body_text(self) -> str:
        """正文纯文本。

        只取顶层章节的跨度：章节的 raw/plain 已是「子树跨度」（含子标题内容），
        若把所有层级都拼起来会重复计数。同时排除参考文献与致谢。
        """
        if not self.sections:
            return self.plain
        skip = ("reference", "bibliograph", "参考文献", "致谢", "acknowledg")
        top = min(s.level for s in self.sections)
        return "\n".join(
            s.plain for s in self.sections
            if s.level == top and not any(k in s.key for k in skip)
        )

    def find_section(self, *keywords: str) -> Section | None:
        for s in self.sections:
            if any(k in s.key for k in keywords):
                return s
        return None


# ---------------------------------------------------------------- 文本工具


def strip_tex_comments(text: str) -> str:
    out = []
    for line in text.split("\n"):
        i, n = 0, len(line)
        cut = n
        while i < n:
            ch = line[i]
            if ch == "\\":
                i += 2
                continue
            if ch == "%":
                cut = i
                break
            i += 1
        out.append(line[:cut])
    return "\n".join(out)


def tex_to_plain(tex: str) -> str:
    t = re.sub(r"\\(?:begin|end)\s*\{[^}]*\}", " ", tex)
    t = re.sub(r"\\[a-zA-Z@]+\*?\s*(?:\[[^\]]*\])?", " ", t)
    t = re.sub(r"\\.", " ", t)
    t = t.replace("{", "").replace("}", "").replace("~", " ")
    # LaTeX 里单个换行只等于空格，空行才是分段。源码硬换行不能当作
    # 段落或句子边界，否则句长、段长统计会全部失真。
    t = re.sub(r"\n[ \t]*\n[ \t\n]*", "\x00", t)
    t = re.sub(r"\s*\n\s*", " ", t)
    t = t.replace("\x00", "\n\n")
    t = re.sub(r"[ \t]{2,}", " ", t)
    return t.strip()


def _extract_group(text: str, open_brace: int) -> str:
    """从 open_brace 处的 '{' 开始取到配对的 '}'。"""
    depth, i, n = 0, open_brace, len(text)
    while i < n:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[open_brace + 1:i]
        i += 1
    return text[open_brace + 1:]


def _strip_braced_commands(text: str, *names: str) -> str:
    """移除 \\thanks{...} 这类带配对花括号的命令及其内容。

    ACM 模板常见写法：\\title{...\\thanks{...}}。不做这步会把致谢段落
    当成标题的一部分。
    """
    for name in names:
        pattern = re.compile(r"\\" + name + r"\s*\{")
        while True:
            m = pattern.search(text)
            if not m:
                break
            inner = _extract_group(text, m.end() - 1)
            text = text[: m.start()] + text[m.end() + len(inner) + 1:]
    return text


def _one_line(s: str) -> str:
    return " ".join(s.split())


def word_stats(text: str) -> dict:
    """英文按空格切词，中文按字计。"""
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    latin_words = len(re.findall(r"[A-Za-z][A-Za-z'\-]*", text))
    sentences = [s for s in re.split(r"(?<=[.!?。！？])\s+|\n+", text) if s.strip()]
    sent_lens = [len(re.findall(r"[A-Za-z][A-Za-z'\-]*", s)) + len(re.findall(r"[\u4e00-\u9fff]", s))
                 for s in sentences]
    paragraphs = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    return {
        "words": latin_words,
        "cjk": cjk,
        "units": latin_words + cjk,
        "sentences": len(sentences),
        "mean_sentence": round(sum(sent_lens) / len(sent_lens), 1) if sent_lens else 0.0,
        "long_sentences": [s for s, ln in zip(sentences, sent_lens) if ln > 45],
        "paragraphs": len(paragraphs),
        "sent_lens": sent_lens,
    }


def passive_ratio(text: str) -> float:
    sents = [s for s in re.split(r"(?<=[.!?。！？])\s+|\n+", text) if s.strip()]
    if not sents:
        return 0.0
    pat = re.compile(
        r"\b(?:is|are|was|were|be|been|being|get|gets|got)\s+(?:\w+ly\s+)?"
        r"(?:\w+(?:ed|en)|written|shown|found|given|made|done|taken|seen|known|used|"
        r"built|held|set|put|run|drawn)\b",
        re.I,
    )
    n = sum(1 for s in sents if pat.search(s))
    return round(n / len(sents), 3)


# ---------------------------------------------------------------- .bib 解析


def parse_bib(path: Path) -> tuple[dict[str, dict], list[str]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    entries: dict[str, dict] = {}
    duplicates: list[str] = []
    for m in _BIB_ENTRY_RE.finditer(text):
        etype, key = m.group(1).lower(), m.group(2).strip()
        if etype in ("string", "comment", "preamble"):
            continue
        depth, i, n = 1, m.end(), len(text)
        while i < n and depth:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        block = text[m.end(): i - 1]
        fields: dict[str, str] = {}
        for fm in _BIB_FIELD_RE.finditer(block):
            name, val = fm.group(1).lower(), fm.group(2).strip()
            if val.startswith("{") and val.endswith("}"):
                val = val[1:-1]
            elif val.startswith('"') and val.endswith('"'):
                val = val[1:-1]
            fields[name] = " ".join(val.split())
        fields["__type"] = etype
        if key in entries:
            duplicates.append(key)
        entries[key] = fields
    return entries, duplicates


def find_bib_files(tex_path: Path, tex_raw: str) -> list[Path]:
    found: list[Path] = []
    for m in _BIBFILE_RE.finditer(tex_raw):
        for name in m.group(1).split(","):
            name = name.strip()
            if not name:
                continue
            p = Path(name) if name.lower().endswith(".bib") else Path(name + ".bib")
            cand = (tex_path.parent / p).resolve()
            if cand.is_file():
                found.append(cand)
    if not found:
        for cand in sorted(tex_path.parent.glob("*.bib")):
            found.append(cand)
    return found


def parse_inline_bib(tex_raw: str) -> dict[str, dict]:
    """解析 \\begin{thebibliography} + \\bibitem 内联文献表。

    单文件投稿（Overleaf 打包）常用这种写法，不应被当成「没有文献库」。
    年份从可选标签里取，如 \\bibitem[Do et al.(2023)]{do2023}。
    """
    out: dict[str, dict] = {}
    for m in _THEBIB_RE.finditer(tex_raw):
        for bm in _BIBITEM_RE.finditer(m.group(1)):
            label = (bm.group(1) or "").strip()
            key = bm.group(2).strip()
            if not key:
                continue
            year = ""
            ym = re.search(r"(19|20)\d{2}", label)
            if ym:
                year = ym.group(0)
            out[key] = {"year": year, "label": label, "__type": "inline"}
    return out


# ---------------------------------------------------------------- 各格式解析


def _sections_from_spans(items: list[tuple[int, str, int]], raw: str, plain_fn) -> list[Section]:
    """items: (level, title, start_offset)，已按位置排序。

    每个章节的正文取「子树跨度」：到下一个同级或更高级标题为止。这样父章节
    的正文包含其下所有子小节，避免「只有子标题的章节被算成空章节」。
    """
    n = len(items)
    sections: list[Section] = []
    for idx, (level, title, start) in enumerate(items):
        end = len(raw)
        for j in range(idx + 1, n):
            if items[j][0] <= level:
                end = items[j][2]
                break
        body = raw[start:end]
        sections.append(Section(level, title.strip(), body, plain_fn(body), idx))
    return sections


def _load_tex(path: Path, raw: str) -> Doc:
    cleaned = strip_tex_comments(raw)

    heads = [(m.group("cmd"), m.group("title"), m.start())
             for m in _SEC_RE.finditer(cleaned)]
    items = [(_SEC_LEVEL[cmd], title, pos) for cmd, title, pos in heads]
    sections = _sections_from_spans(items, cleaned, tex_to_plain)

    cites: Counter = Counter()
    for m in _CITE_RE.finditer(cleaned):
        for key in m.group(2).split(","):
            key = key.strip()
            if key:
                cites[key] += 1

    title = ""
    m = _TITLE_RE.search(cleaned)
    if m:
        raw_title = _extract_group(cleaned, m.end() - 1)
        title = _one_line(tex_to_plain(
            _strip_braced_commands(raw_title, "thanks", "footnotetext", "authornote")
        ))

    authors = ""
    m = _AUTHOR_RE.search(cleaned)
    if m:
        raw_author = _extract_group(cleaned, m.end() - 1)
        authors = _one_line(tex_to_plain(
            _strip_braced_commands(raw_author, "thanks", "footnotetext", "authornote")
        ))

    abstract = ""
    m = _ABSTRACT_RE.search(cleaned)
    if m:
        abstract = tex_to_plain(m.group(1))

    bib_paths = find_bib_files(path, cleaned)
    bib: dict[str, dict] = {}
    dups: list[str] = []
    for bp in bib_paths:
        e, d = parse_bib(bp)
        bib.update(e)
        dups.extend(d)

    # 内联文献表（\begin{thebibliography} + \bibitem），有 .bib 时以 .bib 为准
    for key, fields in parse_inline_bib(cleaned).items():
        bib.setdefault(key, fields)

    return Doc(
        path=path,
        kind="tex",
        raw=cleaned,
        plain=tex_to_plain(cleaned),
        sections=sections,
        cites=cites,
        bib=bib,
        bib_paths=bib_paths,
        bib_duplicates=dups,
        labels=set(_LABEL_RE.findall(cleaned)),
        refs=_REF_RE.findall(cleaned),
        figures=len(re.findall(r"\\begin\{figure\*?\}", cleaned)),
        tables=len(re.findall(r"\\begin\{table\*?\}", cleaned)),
        title=title,
        authors=authors,
        abstract=abstract,
    )


def _load_md(path: Path, raw: str) -> Doc:
    lines = raw.split("\n")
    items: list[tuple[int, str, int]] = []
    offset = 0
    title = ""
    for line in lines:
        m = _MD_HEAD_RE.match(line)
        if m:
            level, text = len(m.group(1)), m.group(2).strip()
            if level == 1 and not title:
                title = text
            items.append((level, text, offset))
        offset += len(line) + 1

    # 唯一的 H1 视为文档标题而非章节，否则顶层跨度会覆盖全文（含参考文献）
    if len(items) > 1 and sum(1 for it in items if it[0] == 1) == 1:
        items = [it for it in items if it[0] != 1]

    sections = _sections_from_spans(items, raw, lambda s: s)

    cites: Counter = Counter()
    for m in _MD_CITE_RE.finditer(raw):
        cites[m.group(1)] += 1

    abstract = ""
    sec = next((s for s in sections if "abstract" in s.key or "摘要" in s.key), None)
    if sec:
        abstract = sec.plain

    return Doc(
        path=path,
        kind="md",
        raw=raw,
        plain=raw,
        sections=sections,
        cites=cites,
        title=title,
        abstract=abstract,
        figures=len(re.findall(r"!\[[^\]]*\]\([^)]*\)", raw)),
    )


def _load_docx(path: Path) -> Doc:
    try:
        with zipfile.ZipFile(path) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except (KeyError, zipfile.BadZipFile) as e:
        raise ValueError(f"不是有效的 .docx：{path}") from e

    paras: list[tuple[int, str]] = []
    for p in re.findall(r"<w:p\b.*?</w:p>", xml, re.S):
        style = re.search(r'<w:pStyle w:val="([^"]+)"', p)
        text = "".join(re.findall(r"<w:t(?:\s[^>]*)?>(.*?)</w:t>", p, re.S))
        text = " ".join(htmllib.unescape(text).split())
        if not text:
            continue
        level = 0
        if style:
            v = style.group(1).lower()
            m = re.search(r"heading\s*(\d)|^h(\d)$", v)
            if m:
                level = int(m.group(1) or m.group(2))
        paras.append((level, text))

    raw = "\n\n".join(t for _, t in paras)
    items: list[tuple[int, str, int]] = []
    offset = 0
    for level, text in paras:
        if level:
            items.append((level, text, offset))
        offset += len(text) + 2

    if len(items) > 1 and sum(1 for it in items if it[0] == 1) == 1:
        items = [it for it in items if it[0] != 1]

    sections = _sections_from_spans(items, raw, lambda s: s)
    title = next((t for lv, t in paras if lv == 1), "")
    abstract = ""
    for s in sections:
        if "abstract" in s.key or "摘要" in s.key:
            abstract = s.plain
            break

    return Doc(
        path=path, kind="docx", raw=raw, plain=raw, sections=sections,
        title=title, abstract=abstract,
    )


def load(path: str | Path) -> Doc:
    p = Path(path).expanduser()
    if not p.is_file():
        raise FileNotFoundError(f"找不到文件：{p}")
    ext = p.suffix.lower()

    if ext == ".docx":
        return _load_docx(p)

    raw = p.read_text(encoding="utf-8", errors="replace")
    if ext == ".doc":
        raise ValueError("不支持旧版 .doc，请另存为 .docx")
    if ext in TEX_EXTS:
        return _load_tex(p, raw)
    if ext in MD_EXTS:
        return _load_md(p, raw)
    # 未知扩展名：按纯文本处理
    return _load_md(p, raw)
