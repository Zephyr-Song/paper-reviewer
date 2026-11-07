# paper-reviewer

学术论文体检与审稿助手。一个 WorkBuddy Skill，也是一个独立命令行工具：用脚本做**确定性检查**，用评审方法论做**判断**。

> 仅需 Python 3.10+。支持 `.tex` / `.md` / `.docx` / `.txt` / `.pdf`（PDF 需 `pip install pypdf`）。

## 为什么分成两层

学术审稿的价值分两类，混在一起做会两头不靠：

| 类型 | 例子 | 该由谁做 |
| --- | --- | --- |
| 确定性 | 引用键是否存在于 `.bib`、双盲稿是否泄露作者名、有没有 TODO、缺哪个章节 | **脚本**。可复现、不遗漏、能进 CI |
| 判断 | 贡献是否够、实验是否支撑结论、论证是否有漏洞 | **模型**。靠 `references/review-rubric.md` 的五维标准 |

所以这个项目不调外部 API：脚本负责「你肯定改漏了什么」，方法论负责「这篇论文到底行不行」。

## 特性

- **37 项检查**，分结构 / 引用 / 匿名 / 文风 / 报告规范 / 摘要一致六类
- **双盲泄露扫描**：作者字段、邮箱、GitHub 链接、自引表述、致谢与资助（自动放行 `anonymous` 镜像）
- **引用双向核对**：正文引用 vs `.bib` 条目，检出缺失键、未引用条目、重复键
- **支持内联文献表**：`\begin{thebibliography}` + `\bibitem`（单文件投稿）同样能核对
- **生成式 AI 声明检测**：ACM/CHI 强制要求，未写会提示
- **样本量一致性**：正文出现多个 `N = xxx` 时提示核实
- **多种口径**：`chi` / `acm` / `neurips` / `thesis` / `generic`，决定必需章节集合
- **摘要一致性**：正文有量化结果而摘要只写「我们做了评估」时报警
- **CI 可用**：`--strict` 在有严重问题时返回退出码 1
- **中文/英文论文都支持**：章节别名含中文（摘要 / 引言 / 相关工作 / 方法 / 结果 / 讨论 / 局限 / 结论）

## 安装

### 作为 WorkBuddy Skill

```bash
git clone https://github.com/Zephyr-Song/paper-reviewer.git \
  ~/.workbuddy/skills/paper-reviewer
```

装好后说「帮我检查这篇论文」或「模拟审稿」即可触发。

### 作为独立命令行

```bash
git clone https://github.com/Zephyr-Song/paper-reviewer.git
cd paper-reviewer
python scripts/papercheck.py --list-checks
```

## 用法

```bash
# 通用体检
python scripts/papercheck.py paper.tex

# CHI 投稿版（自动开双盲检查，要求 Limitations 章节）
python scripts/papercheck.py paper.tex --venue chi --blind

# Word 稿件
python scripts/papercheck.py thesis.docx --venue thesis

# Markdown + 手动指定文献库
python scripts/papercheck.py notes.md --bib refs.bib

# 只报中等以上问题，可接 CI
python scripts/papercheck.py paper.tex --min-severity med --strict

# 机器可读
python scripts/papercheck.py paper.tex --format json -o report.json
```

### 参数

| 参数 | 默认 | 说明 |
| --- | --- | --- |
| `path` | — | 论文文件 |
| `--bib` | 自动发现 | 指定 `.bib` 文献库 |
| `--venue` | `generic` | `chi` / `acm` / `neurips` / `thesis` / `generic` |
| `--blind` / `--no-blind` | `chi`/`acm` 默认开 | 双盲匿名检查 |
| `--min-severity` | `low` | 报告保留的最低级别 |
| `--format` | `md` | `md` / `json` |
| `-o, --out` | — | 写入文件 |
| `--strict` | off | 有严重问题时退出码 1 |
| `--list-checks` | — | 列出全部检查项 |

退出码：`0` 正常，`1` `--strict` 且有严重问题，`3` 解析失败。

## 检查项

| 类别 | 检查项 |
| --- | --- |
| **STR 结构** | 缺必需章节、过短/空章节、讨论与局限篇幅过薄、缺摘要、缺标题、章节层级跳跃、未识别到章节结构 |
| **CIT 引用** | 引用了不存在的文献、存在未引用条目、未找到文献库、无正文引用、重复键、近五年文献占比偏低 |
| **ANO 匿名** | 作者未匿名、出现邮箱、出现可识别链接、自引表述未匿名、存在致谢与资助 |
| **STY 文风** | 过度断言、超长句、超长段、被动语态偏高、未清理占位符、模糊量词偏多、术语不一致、排版瑕疵、novel 过频 |
| **REP 规范** | 缺伦理/IRB、缺知情同意、缺数据可用性、缺代码可用性、缺生成式 AI 声明、样本量不一致、局限过于简略 |
| **ABS 摘要** | 摘要无量化结果、摘要数字在正文无对应、结论未呼应量化结果 |

完整列表：`python scripts/papercheck.py --list-checks`

## 输出示例

```
# 论文体检报告

- 文件：`paper.tex`（tex）
- 正文：5 节 · 英文 52 词 · 平均句长 3.7 词
- 引用：正文 2 处 / 2 个键 · 文献库 2 条
- 评审口径：venue=chi · 双盲=是

**严重 6 · 中等 6 · 提示 5**

| 类别 | 严重 | 中等 | 提示 |
| --- | --- | --- | --- |
| 结构 | 1 | 1 | 0 |
| 引用 | 2 | 0 | 1 |
| 匿名 | 3 | 1 | 0 |

## 🔴 严重（6）

### [ANO-001] 作者信息未匿名

作者字段包含具体姓名/单位，双盲评审会直接泄露身份。

- `Jane Doe · Tsinghua University · jane@tsinghua.edu.cn`

> 投稿版填 Anonymous Author(s)，录用版再换回。
```

## 架构

```
paper.tex ──► docmodel.py ──► checks_*.py ──► papercheck.py ──► 报告
               │                │
               │                ├─ structure  章节与完整性
               │                ├─ citation   引用双向核对
               │                ├─ anonymize  双盲泄露
               │                ├─ style      文风可读性
               │                └─ reporting  声明与规范
               └─ 统一文档模型：章节、正文、引用键、bib、图表
                  （.tex 解析 \section/\cite/\label/.bib；.docx 解析 pStyle 标题）
```

评审方法论与写作清单在 `references/`：

- `review-rubric.md` —— 五维评分标准与锚点、常见拒稿理由、各会议口径差异、意见写法
- `writing-playbook.md` —— 逐节检查清单、贡献声明公式、效度威胁模板、英文表达常见坑

## 测试

```bash
python tests/test_papercheck.py -v
```

22 项测试，用「问题论文」和「规范论文」两份夹具同时验证**检出率**与**误报率**，覆盖 LaTeX/Markdown/DOCX 三种输入、口径切换、匿名开关、JSON 输出、CI 退出码，以及 ACM 模板 `\title{...\thanks{...}}` 这类真实排版回归。

## 已知限制

- 自定义引用宏（`\newcommand{\mycite}`）不被识别，需用 `--bib` 或人工确认
- 不解析 LaTeX 宏展开，`\input{}` 的子文件内容不在检查范围
- 英文文风检查为主；中文论文只看占位符、术语一致性与结构
- **PDF 只做文本抽取，不推断章节层级**，因此结构类检查会自动跳过（见 STR-007）；扫描件需先 OCR
- 表单、申请表、审批单不是论文，体检结论基本不适用——这类文件请人工审阅
- `.doc` 旧格式不支持，请另存为 `.docx`
- 章节识别基于标题关键词，非标准命名可能漏判（会提示「现有章节」供人工判断）

## License

[MIT](LICENSE) © 2026 Zephyr-Song
