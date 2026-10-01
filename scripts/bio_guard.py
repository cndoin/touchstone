#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# SPDX-License-Identifier: MIT
"""bio_guard.py —— 生物医学分析声明核查（19-bio-mode 闸门）

它**不**判断"基因是否真实存在""通路 ID 与名称是否对应""数值算得对不对"——
前两者要查数据库，后者已由 hardcheck.py / cp_lint.py / sc_lint.py 覆盖。
它只保证一件事：**格式与口径层面没有幻觉**。

八个检查器（详见 references/19-bio-mode.md 第 5 节）：

  species   物种锁定 / 命名风格冲突 / 线粒体前缀 / Ensembl 物种码冲突
  gene      基因符号形态（占位符、非法字符、跨物种同源未标注）
  id        ID 体系识别与混用（Ensembl / RefSeq / KEGG / GO / Reactome ...）
  orgdb     organism= 与注释库、物种的配对（含 R 脚本调用抽取）
  stat      统计口径三连 / 伪重复 / 随机种子与版本
  numeric   印象式数值表述 / 数值声明清单
  overclaim 外推三闸越界表述（体外→体内 / 动物→人 / 相关→因果）
  citation  PMID / DOI 格式

用法：
  python3 bio_guard.py --file report.md
  python3 bio_guard.py --file analysis.R --only orgdb,stat
  python3 bio_guard.py --root . --exclude 'references/*' --offline --strict --json

适用范围（重要）：
  它面向**待交付的分析产物**（分析报告、R/Python 脚本、结果摘要）。
  **不要拿去扫教学/规范类文档** —— 那类文档成篇都是故意写错的示例，
  扫出来是一屏假红，反而把真问题淹掉。需要扫目录时用 --exclude 把
  references/ 、docs/ 这类目录排掉。

退出码：0=全部通过 1=存在失败 2=存在需人工确认项 3=用法错误
原则：**查不出的不假装查过**——只能判"形态与口径"，判不了"科学性"，后者交给人。
"""

import fnmatch
import io
import os
import re
import sys
import tokenize

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from _common import (  # noqa: E402
    ArgParser,
    EXIT_UNVERIFIED,
    EXIT_USAGE,
    FAIL,
    PASS,
    UNVERIFIED,
    emit,
    err,
    exit_code_for,
    make_result,
    status_symbol,
    summarize,
    _force_utf8,
)

# ---------------------------------------------------------------------------
# 0. 基础数据：物种定义与命名规则
# ---------------------------------------------------------------------------

# 物种 → 判据词表 / 命名风格 / Ensembl 前缀 / KEGG 代码 / 注释库
#
# strong = 明确的物种词，出现即可锁定；weak = 基因组代号等弱证据，仅在无 strong 时兜底。
# **注释库名（org.Xx.eg.db）刻意不进任何一列** —— 否则 `org.Hs.eg.db` 会把 human 塞进
# 物种集合，让"注释库与物种不符"这条检查自我消解（这是实现期实测踩到的坑）。
SPECIES_DEF = {
    "human": {
        "strong": ["人类", "人源", "人样本", "homo sapiens", "human"],
        "weak": ["hg19", "hg38", "grch37", "grch38"],
        "style": "upper",
        "ensembl": "ENSG",
        "kegg": "hsa",
        "orgdb": "org.hs.eg.db",
        "mt_prefix": "MT-",
    },
    "mouse": {
        "strong": ["小鼠", "mus musculus", "mouse", "mice"],
        "weak": ["mm10", "mm39", "grcm38", "grcm39"],
        "style": "title",
        "ensembl": "ENSMUSG",
        "kegg": "mmu",
        "orgdb": "org.mm.eg.db",
        "mt_prefix": "mt-",
    },
    "rat": {
        "strong": ["大鼠", "rattus norvegicus", "rat"],
        "weak": ["rn6", "rn7", "mratbn7"],
        "style": "title",
        "ensembl": "ENSRNOG",
        "kegg": "rno",
        "orgdb": "org.rn.eg.db",
        "mt_prefix": "mt-",
    },
    "zebrafish": {
        "strong": ["斑马鱼", "danio rerio", "zebrafish"],
        "weak": ["danrer11", "grcz11"],
        "style": "lower",
        "ensembl": "ENSDARG",
        "kegg": "dre",
        "orgdb": "org.dr.eg.db",
        "mt_prefix": "mt-",
    },
    "fly": {
        "strong": ["果蝇", "drosophila", "fruit fly"],
        "weak": ["bdgp6", "dm6"],
        "style": "lower",
        "ensembl": "FBgn",
        "kegg": "dme",
        "orgdb": "org.dm.eg.db",
        "mt_prefix": "mt-",
    },
    "worm": {
        "strong": ["线虫", "caenorhabditis elegans", "c. elegans"],
        "weak": ["wbcel235"],
        "style": "lower",
        "ensembl": "WBGene",
        "kegg": "cel",
        "orgdb": "org.ce.eg.db",
        "mt_prefix": "mt-",
    },
}

SPECIES_ZH = {
    "human": "人类", "mouse": "小鼠", "rat": "大鼠",
    "zebrafish": "斑马鱼", "fly": "果蝇", "worm": "线虫",
}

# Ensembl 前缀 → 物种（用于揪出"物种与 ID 不配"）
ENSEMBL_PREFIX_RE = [
    (re.compile(r"\bENSMUSG\d{11}\b"), "mouse"),
    (re.compile(r"\bENSRNOG\d{11}\b"), "rat"),
    (re.compile(r"\bENSDARG\d{11}\b"), "zebrafish"),
    (re.compile(r"\bENSG\d{11}\b"), "human"),
    (re.compile(r"\bFBgn\d{7}\b"), "fly"),
    (re.compile(r"\bWBGene\d{8}\b"), "worm"),
]

# KEGG 通路前缀 → 物种
KEGG_PATH_RE = re.compile(r"\b(hsa|mmu|rno|dre|dme|cel|sce|ath)\d{5}\b")
# miRBase 前缀 → 物种
MIRBASE_RE = re.compile(r"\b(hsa|mmu|rno|dre|dme|cel)-(?:miR|let)-\d+[a-z]*(?:-\d+p)?\b")

# 注释库白名单（OrgDb 类包名）
KNOWN_ORGDB = {
    "org.hs.eg.db": "human", "org.mm.eg.db": "mouse", "org.rn.eg.db": "rat",
    "org.dr.eg.db": "zebrafish", "org.dm.eg.db": "fly", "org.ce.eg.db": "worm",
    "org.sc.sgd.db": None, "org.at.tair.db": None, "org.bt.eg.db": None,
}

# 接受「三字母 KEGG 代码」的函数 —— 传学名即错（静默返回 UNKNOWN）
KEGG_CODE_FUNCS = {
    "enrichKEGG", "gseKEGG", "enrichMKEGG", "gseMKEGG",
    "download_KEGG", "gson_KEGG", "search_kegg_organism",
}
# 接受「拉丁学名」的函数 —— 传代码即错
WP_NAME_FUNCS = {"enrichWP", "gseWP", "enrichWP_"}

# 常见非基因的大写缩写（避免把它们当基因符号做风格判定）
NON_GENE_ACRONYMS = {
    "DNA", "RNA", "MRNA", "CDNA", "PCR", "QPCR", "RTPCR", "GO", "KEGG", "DE",
    "FC", "PCA", "UMAP", "TSNE", "SCT", "QC", "FDR", "BH", "BY", "SD", "SE",
    "CI", "HR", "OR", "RR", "ANOVA", "GWAS", "MR", "SMR", "HEIDI", "SNP",
    "LD", "IV", "WGS", "WES", "ATAC", "CHIP", "RIP", "FISH", "IF", "IHC",
    "WB", "ELISA", "NGS", "RNAI", "SHRNA", "SIRNA", "CRISPR", "CAS9", "KO",
    "KI", "WT", "OE", "KD", "TPM", "RPKM", "FPKM", "CPM", "FASTQ", "BAM",
    "SAM", "VCF", "GFF", "GTF", "BED", "CSV", "TSV", "JSON", "HTML", "API",
    "URL", "DOI", "PMID", "PNG", "PDF", "SVG", "CNV", "SV", "GSEA", "ORA",
    "NES", "ES", "HVG", "PBMC", "WGCNA", "MHC", "HLA", "BCR", "TCR", "IG",
    "MT", "NA", "NAN", "TRUE", "FALSE", "NULL", "SUM", "MAX", "MIN", "ID",
    "CLR", "PA", "PVAL", "PADJ", "SEED", "MAD", "IQR", "VST", "RLE", "TMM",
    "FDR", "BH", "EFDR", "LFC", "MLE", "EM", "GLM", "GAM", "LMM", "PC",
    "UMAP", "R", "PYTHON", "RSTUDIO", "GEO", "TCGA", "GTEX", "CCLE", "SRA",
}

# 线粒体前缀（人 MT- / 其他 mt-）
RE_MT_HUMAN = re.compile(r"\bMT-[A-Z0-9]{1,6}\b")
RE_MT_OTHER = re.compile(r"\bmt-[A-Za-z0-9]{1,6}\b")

# 基因候选：2–10 位的字母+数字组合
RE_GENE_UPPER = re.compile(r"\b[A-Z][A-Z0-9]{1,9}\b")
# 真基因符号的第 2 位必是小写字母（Trp53 / Gapdh / Actb）。
# 早期写成 [A-Z][a-z0-9]{1,9}，于是 E402 这类「字母+数字」的
# lint 码同时命中 UPPER 与 TITLE 两个正则，被判成"同一基因两种命名风格"。
RE_GENE_TITLE = re.compile(r"\b[A-Z][a-z][A-Za-z0-9]{0,8}\b")

# 全角标点（落在代码 token 里会让解释器直接报语法错）
RE_FULLWIDTH_PUNCT = re.compile(
    r"[\uff08\uff09\uff3b\uff3d\uff5b\uff5d\u3014\u3015"
    r"\uff1b\uff1a\uff0c\uff1c\uff1e\uff1d\uff0b\uff0d\uff0a\uff0f]"
)

# UniProtKB accession 的官方形态：P04637 / Q9Y2X7 / A0A123 —— **必含数字**。
# 早期版本这里是 [A-Z0-9]{2,8}_[A-Z]{2,6}，把 EXIT_OK / SKIP_DIRS / DEFAULT_UA
# 这类「大写下划线常量」全部命中，那不是 accession 而是命名风格，纯误报。
RE_UNIPROT_ACC = re.compile(
    r"\b(?:[OPQ][0-9][A-Z0-9]{3}[0-9]|[A-NR-Z][0-9](?:[A-Z][A-Z0-9]{2}[0-9]){1,2})\b"
)

# 占位符基因（没填真名就交付的信号）
RE_PLACEHOLDER_GENE = re.compile(
    r"\b(?:GENE|Gene|gene)[-_]?([A-Z]|\d{1,2})\b|\bProtein[-_]?[A-Z]\b|\b(geneX|geneY|geneZ)\b"
)

# 跨物种同源标注（出现这些词就不算"未标注混用"）
CROSS_SPECIES_MARKERS = [
    "同源", "直系同源", "旁系同源", "homolog", "ortholog", "paralog",
    "对应的人", "对应的小鼠", "人鼠", "跨物种", "直系", "同源基因",
]

# ---------------------------------------------------------------------------
# 1. 通用工具
# ---------------------------------------------------------------------------

SKIP_DIRS = {
    ".git", "node_modules", ".touchstone", "__pycache__", ".venv", "venv",
    "dist", "build", ".idea", ".vscode", ".mypy_cache", ".pytest_cache",
    "site-packages", ".Rproj.user", "renv",
}

SCAN_EXT = {
    ".r": "script", ".rmd": "script", ".py": "script", ".sh": "script",
    ".md": "report", ".txt": "report", ".json": "report", ".csv": "report",
    ".tsv": "report", ".html": "report",
}

MAX_FILE_BYTES = 2 * 1024 * 1024  # 单文件上限 2 MB，超出截断
MAX_TARGETS = 400                 # 目录扫描文件数上限


def _code_only(text, path):
    """剥掉注释与字符串字面量，只留下代码 token。返回 (code_text, exact)。

    为什么必须剥：全角标点检查的意图是"这段代码照原样执行会报语法错"，
    而注释与字符串里的全角标点**完全合法**（中文说明、中文提示语）。
    不剥的话，任何带中文注释的脚本都必然 FAIL —— 恒红的检查等于没有信号，
    和"无网必红"是同一类缺陷。

    Python 用标准库 tokenize 精确切分；其它语言没有等价物，退化为保守的
    行内剥离。tokenize 失败（语法不完整）时同样降级，但 exact=False
    会告诉调用方"这不是精确结果"。
    """
    if path.lower().endswith(".py"):
        try:
            parts = []
            for t in tokenize.generate_tokens(io.StringIO(text).readline):
                if t.type in (tokenize.COMMENT, tokenize.STRING,
                              tokenize.NL, tokenize.NEWLINE,
                              tokenize.INDENT, tokenize.DEDENT):
                    continue
                parts.append(t.string)
            return " ".join(parts), True
        except Exception:  # noqa: BLE001  语法不完整时降级，绝不因此放弃检查
            pass
    return _strip_comments_heuristic(text), False


def _strip_comments_heuristic(text):
    """非 Python 语言的保守剥离：先去成对引号内容，再去 # 注释。"""
    out = []
    for line in text.splitlines():
        line = re.sub(r"""["][^"\n]*["]|['][^'\n]*[']""", " ", line)
        i = line.find("#")
        if i >= 0:
            line = line[:i]
        out.append(line)
    return "\n".join(out)


def _match_label(text_lower, label):
    """ASCII 词用词边界匹配（否则 rat 会命中 rate/generate/ratio）；中文直接子串。"""
    if label.isascii():
        return re.search(r"\b" + re.escape(label) + r"\b", text_lower) is not None
    return label in text_lower


def detect_species(text_lower):
    """返回文本中出现的物种集合。

    分两档：strong（明确物种词）优先；strong 全空时才用 weak（基因组代号）兜底。
    这样 `org.Hs.eg.db` + 「小鼠」不会被判成"人鼠双物种"，从而让冲突检查能真正生效。
    """
    strong, weak = set(), set()
    for sp, spec in SPECIES_DEF.items():
        if any(_match_label(text_lower, lb) for lb in spec["strong"]):
            strong.add(sp)
        elif any(_match_label(text_lower, lb) for lb in spec["weak"]):
            weak.add(sp)
    return strong if strong else weak


def has_cross_species_marker(text_lower):
    return any(m.lower() in text_lower for m in CROSS_SPECIES_MARKERS)


def split_sentences(text):
    """按中英文句末标点切句，用于"越界表述附近有没有限定词"的判定。"""
    parts = re.split(r"(?<=[。！？；\n])|(?<=[.!?])\s+", text)
    return [p.strip() for p in parts if p and p.strip()]


HEDGE_WORDS = [
    "可能", "提示", "潜在", "推测", "有待", "需进一步", "尚需", "待验证",
    "尚不明确", "需要验证", "不能排除", "需独立", "有待验证", "初步",
    "may", "might", "suggest", "potential", "possibly", "further",
]


def sentence_of(text, pos):
    """取 pos 所在的句子（用于限定词检查）。"""
    start = max(text.rfind("\n", 0, pos), text.rfind("。", 0, pos),
                text.rfind("；", 0, pos), text.rfind(". ", 0, pos))
    end_candidates = [text.find(c, pos) for c in ("\n", "。", "；", ". ")]
    ends = [e for e in end_candidates if e != -1]
    end = min(ends) if ends else len(text)
    return text[start + 1:end].strip()


def has_hedge(sentence):
    low = sentence.lower()
    return any(h in low for h in HEDGE_WORDS)


def r(path, text, status, detail, evidence=""):
    """结果工厂。

    kind 先留空，由 run_checks() 按**发出它的检查器名**回填 ——
    只有调用侧知道这批结果属于谁，检查器内部不必（也无法）重复声明。

    历史缺陷：早期版本这里写的是 make_result(path, path, ...)，
    于是 kind 字段被填成了文件路径，下游按检查器聚合全部失真。
    """
    return make_result("", path, status, detail, evidence)


def line_of(text, pos):
    return text.count("\n", 0, pos) + 1


# ---------------------------------------------------------------------------
# 2. 检查器
# ---------------------------------------------------------------------------

def check_species(path, text, kind, cfg):
    """物种锁定 / 命名风格冲突 / 线粒体前缀 / Ensembl 物种码冲突。"""
    out = []
    low = text.lower()
    species = detect_species(low)

    # 2.1 Ensembl 物种码与声明物种冲突（硬判定）
    for pat, sp in ENSEMBL_PREFIX_RE:
        m = pat.search(text)
        if not m:
            continue
        if species and sp not in species:
            declared = "、".join(SPECIES_ZH.get(s, s) for s in sorted(species))
            out.append(r(path, text, FAIL,
                         "Ensembl ID %s 属于%s，但文中物种是「%s」" % (
                             m.group(0)[:20], SPECIES_ZH.get(sp, sp), declared),
                         "位置：第 %d 行" % line_of(text, m.start())))
        elif not species:
            out.append(r(path, text, UNVERIFIED,
                         "出现 Ensembl ID %s（%s），但全文未锁定物种" % (
                             m.group(0)[:20], SPECIES_ZH.get(sp, sp)),
                         "位置：第 %d 行" % line_of(text, m.start())))

    # 2.2 线粒体前缀与物种的一致性（人 MT- / 其他 mt-，这是最容易露馅的地方）
    mt_h = RE_MT_HUMAN.findall(text)
    mt_o = RE_MT_OTHER.findall(text)
    if (mt_h or mt_o) and not has_cross_species_marker(low):
        if mt_h and mt_o:
            out.append(r(path, text, UNVERIFIED,
                         "同时出现人类型 MT- 前缀与其它物种 mt- 前缀（未见跨物种说明）",
                         "MT- 例：%s ｜ mt- 例：%s" % (", ".join(mt_h[:3]), ", ".join(mt_o[:3]))))
        elif species and "human" not in species and mt_h:
            declared = "、".join(SPECIES_ZH.get(s, s) for s in sorted(species))
            out.append(r(path, text, FAIL,
                         "出现人类式 MT- 前缀，但物种锁定为「%s」" % declared,
                         "例：%s ｜ 人用 MT-ND1，%s用 mt-Nd1 这类小写前缀"
                         % (", ".join(mt_h[:3]), declared)))
        elif species and species == {"human"} and mt_o:
            out.append(r(path, text, FAIL,
                         "出现非人类式 mt- 前缀，但物种锁定为「人类」",
                         "例：%s ｜ 人用 MT-ND1" % ", ".join(mt_o[:3])))

    # 2.3 同一基因两种命名风格并存（人类 TP53 vs 小鼠 Trp53）
    upper = {g for g in RE_GENE_UPPER.findall(text) if g not in NON_GENE_ACRONYMS}
    title = {g for g in RE_GENE_TITLE.findall(text)}
    title_lower = {t.lower() for t in title}
    pairs = sorted({u for u in upper if u.lower() in title_lower})
    if pairs and not has_cross_species_marker(low):
        out.append(r(path, text, UNVERIFIED,
                     "同一基因出现两种命名风格（人类式/小鼠式）且未见跨物种说明",
                     "例：%s" % "、".join(pairs[:5])))

    # 2.4 有基因符号但没锁定物种 → 无法判定命名是否合规
    if (upper or title) and not species:
        out.append(r(path, text, UNVERIFIED,
                     "全文出现基因符号但未锁定物种（无法判定命名规范）",
                     "物种只能来自用户输入/数据元信息/实际探测，不许靠推断"))

    return out


def check_gene(path, text, kind, cfg):
    """基因符号形态：占位符、非法字符。"""
    out = []

    # 3.1 占位符基因名（说明符号没填真名就交付了）
    ph = [m.group(0) for m in RE_PLACEHOLDER_GENE.finditer(text)]
    if ph:
        out.append(r(path, text, UNVERIFIED,
                     "出现疑似占位符基因名（未填真实符号）",
                     "例：%s" % "、".join(sorted(set(ph))[:5])))

    # 3.2 全角标点：**只在脚本里、且只在代码部分算错**。
    #     中文正文（.md/.txt）用全角标点是正常的；脚本的注释与字符串里用也是正常的。
    #     只有落在代码 token 里，解释器才会报语法错 —— 所以先剥再查。
    if kind == "script":
        code, exact = _code_only(text, path)
        fw = sorted(set(RE_FULLWIDTH_PUNCT.findall(code)))
        if fw:
            out.append(r(path, text, FAIL,
                         "脚本的代码部分含全角标点（解释器会报语法错）",
                         "例：%s%s" % ("".join(fw[:10]),
                                      "" if exact else " ｜ 已降级为启发式剥离，留意误报")))

    for m in list(RE_UNIPROT_ACC.finditer(text))[:3]:
        out.append(r(path, text, UNVERIFIED,
                     "出现 UniProt accession %s —— 它是蛋白条目号，不是基因符号，别当 SYMBOL 用"
                     % m.group(0),
                     "位置：第 %d 行" % line_of(text, m.start())))

    return out


def check_id(path, text, kind, cfg):
    """ID 体系识别与混用。"""
    out = []
    low = text.lower()
    species = detect_species(low)
    systems = {}

    for name, pat in (
        ("Ensembl 基因", re.compile(r"\b(ENSG|ENSMUSG|ENSRNOG|ENSDARG)\d{11}\b")),
        ("Ensembl 转录本", re.compile(r"\b(ENST|ENSMUST|ENSRNOT|ENSDART)\d{11}\b")),
        ("RefSeq mRNA", re.compile(r"\bN[MR]_\d{6,9}(?:\.\d+)?\b")),
        ("RefSeq 蛋白", re.compile(r"\bN[PX]_\d{6,9}(?:\.\d+)?\b")),
        ("GO term", re.compile(r"\bGO:\d{7}\b")),
        ("KEGG 通路", KEGG_PATH_RE),
        ("KEGG Orthology", re.compile(r"\bK\d{5}\b")),
        ("Reactome", re.compile(r"\bR-[A-Z]{3}-\d+\b")),
        ("WikiPathways", re.compile(r"\bWP\d{3,6}\b")),
        ("miRBase", MIRBASE_RE),
        ("FlyBase", re.compile(r"\bFBgn\d{7}\b")),
        ("WormBase", re.compile(r"\bWBGene\d{8}\b")),
    ):
        m = pat.search(text)
        if m:
            systems[name] = m.group(0)

    # 4.1 KEGG / miRBase / Reactome 前缀与声明物种冲突
    if species:
        for pat, label in ((KEGG_PATH_RE, "KEGG 通路"), (MIRBASE_RE, "miRBase")):
            m = pat.search(text)
            if not m:
                continue
            code = m.group(1)
            sp_of_code = next((s for s, d in SPECIES_DEF.items() if d["kegg"] == code), None)
            if sp_of_code and sp_of_code not in species:
                out.append(r(path, text, FAIL,
                             "%s 前缀「%s」属于%s，与文中物种不符" % (
                                 label, code, SPECIES_ZH.get(sp_of_code, sp_of_code)),
                             "位置：第 %d 行" % line_of(text, m.start())))

        m = re.search(r"\bR-([A-Z]{3})-\d+\b", text)
        if m and m.group(1) == "HSA" and "human" not in species:
            out.append(r(path, text, FAIL,
                         "Reactome ID 用了 R-HSA-（人类），与文中物种不符", m.group(0)))

    # 4.2 体系混用：同一声明里出现多套 ID 却无转换说明
    if len(systems) >= 3:
        has_map = bool(re.search(r"bitr|mapIds|setReadable|ID\s*转换|id\s*mapping|转换", text, re.I))
        if not has_map:
            out.append(r(path, text, UNVERIFIED,
                         "同时出现 %d 套 ID 体系但未见转换说明（keyType 极易配错）" % len(systems),
                         "体系：%s" % "、".join(sorted(systems))))

    return out


# 函数调用头：name(...)。只负责定位到左括号，参数文本由下面手写配对取出。
#
# 为什么不用一条正则把参数也匹配掉：
#   原来是 `([^()]*(?:\([^()]*\)[^()]*)*)` —— 嵌套量词，遇"很长且没有右括号"
#   的文本会退化成 O(n²)。实测 20 万字符的单行把它拖到 120 秒超时
#   （robustness_test 的边界用例抓到的真问题）。
#   标识符长度也限到 64：`[A-Za-z0-9._]*` 贪婪吃掉长串后再逐字符回溯去试
#   `\s*\(`，是同类 O(n²) 的另一个来源。
CALL_HEAD_RE = re.compile(r"([A-Za-z_][A-Za-z0-9._]{0,63})\s*\(")
CALL_MAX_ARGS = 4096   # 单次调用的参数文本上限，超过即不再做 organism 判定


def iter_calls(text):
    """产出 (函数名, 参数文本)。括号配对用手写扫描，整体线性。"""
    for m in CALL_HEAD_RE.finditer(text):
        i = m.end()
        start = i
        depth = 1
        limit = min(len(text), start + CALL_MAX_ARGS)
        while i < limit:
            c = text[i]
            if c == "(":
                depth += 1
            elif c == ")":
                depth -= 1
                if depth == 0:
                    yield m.group(1), text[start:i]
                    break
            i += 1


def check_orgdb(path, text, kind, cfg):
    """organism= / OrgDb 与物种的配对。"""
    out = []
    low = text.lower()
    species = detect_species(low)

    # 5.1 OrgDb 是否在白名单内，且与物种一致
    for m in re.finditer(r"\borg\.[A-Za-z]{2}\.[a-z]{2,4}\.db\b", text):
        pkg = m.group(0).lower()
        if pkg not in KNOWN_ORGDB:
            out.append(r(path, text, UNVERIFIED,
                         "注释库 %s 不在已知 OrgDb 名单里（名字可能是编的）" % m.group(0),
                         "已知：%s" % ", ".join(sorted(KNOWN_ORGDB))))
            continue
        sp = KNOWN_ORGDB[pkg]
        if sp and species and sp not in species:
            out.append(r(path, text, FAIL,
                         "注释库 %s 属于%s，与文中物种不符" % (
                             m.group(0), SPECIES_ZH.get(sp, sp)),
                         "位置：第 %d 行" % line_of(text, m.start())))

    # 5.2 R 调用里的 organism= 语义（这是 cp_lint 查不出的：参数名合法但语义错）
    for fn_raw, args in iter_calls(text):
        fn = fn_raw.split(".")[-1]
        om = re.search(r"organism\s*=\s*[\"']([^\"']+)[\"']", args)
        if om:
            val = om.group(1).strip()
            if fn in KEGG_CODE_FUNCS and not re.fullmatch(r"[a-z]{3,4}", val):
                out.append(r(path, text, FAIL,
                             "%s(organism=\"%s\") —— KEGG 只接受三字母代码" % (fn, val),
                             "应写 hsa/mmu/dre……；传学名会被当 UNKNOWN，结果全空且不报错"))
            elif fn in WP_NAME_FUNCS and re.fullmatch(r"[a-z]{3,4}", val):
                out.append(r(path, text, FAIL,
                             "%s(organism=\"%s\") —— WikiPathways 只接受拉丁学名" % (fn, val),
                             "应写 \"Homo sapiens\" 这类学名"))
            elif fn in KEGG_CODE_FUNCS and re.fullmatch(r"[a-z]{3,4}", val.replace(" ", "")):
                sp_of_code = next((s for s, d in SPECIES_DEF.items() if d["kegg"] == val), None)
                if sp_of_code and species and sp_of_code not in species:
                    out.append(r(path, text, FAIL,
                                 "%s 用了 %s 代码（%s），与文中物种不符" % (
                                     fn, val, SPECIES_ZH.get(sp_of_code, sp_of_code)), ""))

    return out


def check_stat(path, text, kind, cfg):
    """统计口径三连 / 伪重复 / 随机种子。"""
    out = []
    low = text.lower()

    # 必须要求后面跟数字：否则源码里的 `p = ArgParser(...)`、`p.stdout`
    # 都会被判成"报告了 p 值"。NUM_PATTERNS 一直是要求数字的，
    # 两处口径此前不一致 —— 这是"代码被当成统计声明"的根因之一。
    has_p = bool(re.search(r"\bp\s*(?:-?\s*value)?\s*[=<>]\s*[0-9]", low)) or ("p值" in low)
    has_padj = bool(re.search(r"\b(padj|p\.adj|p\.adjust|q\.?\s*value|fdr|adjusted\s*p)\b",
                              low)) or ("校正" in low or "多重检验" in low)

    # 6.1 报 p 值但不提校正
    if has_p and not has_padj:
        out.append(r(path, text, UNVERIFIED,
                     "报告了 p 值但全文未见「校正/FDR/padj/BH」",
                     "差异表达等场景应报 padj 并写明校正方法（BH/Bonferroni/BY）"))

    # 6.2 logFC 未声明底数
    m_fc = re.search(r"log\s*2?\s*FC|log\s*fold\s*change", text, re.I)
    if m_fc:
        seg = text[max(0, m_fc.start() - 120): m_fc.end() + 120].lower()
        if "log2" not in seg and "底数" not in seg and "log 2" not in seg:
            out.append(r(path, text, UNVERIFIED,
                         "出现 logFC 但未声明底数（log2 还是 ln？）",
                         "同一数据 logFC=1 是 2 倍还是 e 倍，差 44%"))

    # 6.3 伪重复风险
    pseudo = (re.search(r"细胞(数|作为|水平)|per\s*cell|单细胞", low)
              and re.search(r"t\s*-?\s*检验|t-test|student'?s", low))
    if pseudo:
        out.append(r(path, text, UNVERIFIED,
                     "单细胞场景直接用 t 检验 —— 警惕伪重复（统计单元应是个体/样本，不是细胞）",
                     "把 5000 个细胞当 5000 个独立样本，p 值会小到荒谬"))

    # 6.4 随机过程未固定种子（脚本模式）
    if kind == "script":
        rand_call = re.search(
            r"\b(RunUMAP|RunTSNE|FindClusters|SCTransform|SketchData|gseGO|gseKEGG|"
            r"RunPCA|FindMarkers|FindAllMarkers|IntegrateLayers|RunMixscape)\s*\(", text)
        if rand_call:
            seed = re.search(r"\b(seed\.use|random\.seed|seed)\s*=", text)
            if not seed:
                out.append(r(path, text, UNVERIFIED,
                             "脚本用了含随机过程的函数（%s）但未固定种子" % rand_call.group(1),
                             "结果不可复现；RunUMAP 用 seed.use=42、FindClusters 用 random.seed=0"))

    return out


RE_VAGUE_NUM = re.compile(
    r"(通常|一般|大约|往往|常见的|一般来说|一般在|typically|usually)[^。；\n]{0,20}?\d"
)
NUM_PATTERNS = [
    ("p", re.compile(r"\bp\s*(?:-?\s*value)?\s*[=<>]\s*([0-9]+(?:\.[0-9]+)?(?:[eE][-+]?\d+)?)")),
    ("padj", re.compile(r"\bpadj\s*[=<>]\s*([0-9]+(?:\.[0-9]+)?(?:[eE][-+]?\d+)?)", re.I)),
    ("logFC", re.compile(r"\blog2?\s*FC\s*[=:]\s*(-?[0-9]+(?:\.[0-9]+)?)", re.I)),
    ("NES", re.compile(r"\bNES\s*[=:]\s*(-?[0-9]+(?:\.[0-9]+)?)")),
    ("HR", re.compile(r"\bHR\s*[=:]\s*([0-9]+(?:\.[0-9]+)?)")),
]


def check_numeric(path, text, kind, cfg):
    """印象式数值表述 / 数值声明清单。"""
    out = []

    # 7.1 "通常/一般 + 数字" —— 凭印象的数值，是编造的高发区
    vague = RE_VAGUE_NUM.search(text)
    if vague:
        out.append(r(path, text, UNVERIFIED,
                     "出现印象式数值表述（「%s…」）—— 数值必须来自执行输出" % vague.group(0)[:24].strip(),
                     "位置：第 %d 行" % line_of(text, vague.start())))

    # 7.2 数值清单（info 用：让使用者逐条接地核对）
    found = []
    for label, pat in NUM_PATTERNS:
        for m in pat.finditer(text):
            found.append("%s=%s@L%d" % (label, m.group(1), line_of(text, m.start())))
    if found and cfg.get("list_numbers"):
        out.append(r(path, text, PASS,
                     "数值声明清单（逐条确认能追到输出文件的具体列）",
                     "；".join(found[:12]) + ("…" if len(found) > 12 else "")))

    return out


OVERCLAIM_RULES = [
    (re.compile(r"(证明|证实|确证|表明了)[^。；\n]{0,25}(导致|引起了?|造成|因果关系)"),
     "因果断言", "观察性数据推不出因果方向，需 MR/干预实验"),
    (re.compile(r"因果(关系)?(已|得到)?(确立|证实|证明|明确)"),
     "因果断言", "需说明 MR 三假设（相关/独立/排他）是否检验"),
    (re.compile(r"(可|能)直接(用于|应用于|指导)临床"),
     "临床外推", "生信标记物需前瞻性队列验证"),
    (re.compile(r"适用于(所有|全部|各类|任何)"),
     "普适断言", "需限定人群/组织/物种范围"),
    (re.compile(r"(所有|全部|每一位)患者"),
     "人群泛化", "需给出亚组特征"),
    (re.compile(r"(毫无|无)疑问|不可否认|必然(会|能|是)|肯定会|一定能"),
     "绝对化", "删除，或改为带置信度的表述"),
    (re.compile(r"(可|能)?(成|作为|是)(为)?(潜在)?(的)?治疗靶点"),
     "靶点断言", "靶点需功能实验验证"),
    (re.compile(r"首次(发现|报道|揭示|证明|提出)"),
     "首次断言", "需查新；查不到就写「未检索到相关报道」"),
]


def check_overclaim(path, text, kind, cfg):
    """外推三闸越界表述（带限定词豁免）。"""
    out = []
    for pat, label, advice in OVERCLAIM_RULES:
        m = pat.search(text)
        if not m:
            continue
        sent = sentence_of(text, m.start())
        if has_hedge(sent):
            continue  # 已带限定词，不算越界
        out.append(r(path, text, UNVERIFIED,
                     "越界表述（%s）：「%s」" % (label, sent[:60]),
                     "第 %d 行 ｜ %s" % (line_of(text, m.start()), advice)))
    return out


RE_PMID = re.compile(r"\bPMID[:：\s]*(\d{1,12})\b", re.I)
RE_DOI = re.compile(r"\b(10\.\d{3,12}/[^\s\"'<>()\[\]，。；]+)", re.I)


def check_citation(path, text, kind, cfg):
    """PMID / DOI 格式校验（存在性走 hardcheck.py）。"""
    out = []
    for m in RE_PMID.finditer(text):
        num = m.group(1)
        if not (6 <= len(num) <= 9):
            out.append(r(path, text, FAIL,
                         "PMID 位数异常：%s（正常 6–9 位）" % num,
                         "位置：第 %d 行" % line_of(text, m.start())))
    for m in RE_DOI.finditer(text):
        doi = m.group(1)
        if not re.match(r"^10\.\d{4,9}/", doi):
            out.append(r(path, text, FAIL,
                         "DOI 注册号格式异常：%s" % doi[:60],
                         "规范形态 10.<4-9位注册号>/<后缀>"))
    if (RE_PMID.search(text) or RE_DOI.search(text)) and not cfg.get("offline"):
        out.append(r(path, text, UNVERIFIED,
                     "文中有文献标识 —— 格式合法不等于存在，请跑 hardcheck.py 解析",
                     "python3 scripts/hardcheck.py --doi <DOI>"))
    return out


CHECKS = [
    ("species", check_species, "物种锁定与命名规范"),
    ("gene", check_gene, "基因符号形态"),
    ("id", check_id, "ID 体系与混用"),
    ("orgdb", check_orgdb, "organism/OrgDb 配对"),
    ("stat", check_stat, "统计口径与复现性"),
    ("numeric", check_numeric, "数值表述"),
    ("overclaim", check_overclaim, "结论外推边界"),
    ("citation", check_citation, "文献标识格式"),
]
CHECK_NAMES = [c[0] for c in CHECKS]


# ---------------------------------------------------------------------------
# 3. 目标收集与主流程
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# 相关性门：目录扫描时，只对"确实涉及生物医学"的文件跑检查
# ---------------------------------------------------------------------------
# 为什么需要：本模块的基因/物种规则是为**文本报告**设计的。拿它去扫普通工程
# 脚本时，BLE001（noqa 码）、MIT（许可证名）、SPDX、EXIT_OK 这些源码标识符
# 会被当成基因符号 —— 几十条假红把真问题全淹掉，闸门失去信号价值。
#
# 安全方向（重要）：判"相关"只会多跑几个检查器（最坏是多几条误报）；
# 判"不相关"会**静默跳过**（漏检风险）。所以信号表刻意取得宽，
# 只有明确不沾边的文件才会被滤掉。
#
# 生效范围：**只对 --root 批量扫描生效**。用户用 --file 显式点名某个文件，
# 说明他知道自己在查什么，一律强制全查，不走这道门 —— 免得它变成放行通道。
BIO_SIGNALS = [
    # 物种名（中文 / 英文 / 拉丁）
    "homo sapiens", "mus musculus", "rattus norvegicus", "danio rerio",
    "drosophila", "caenorhabditis", "人类", "小鼠", "大鼠", "斑马鱼",
    "果蝇", "线虫", "人源", "鼠源",
    # 生信库 / 工具 / 数据库对象
    "clusterprofiler", "org.hs.eg.db", "org.mm.eg.db", "orgdb", "ensembldb",
    "deseq2", "edger", "limma", "seurat", "scanpy", "bioconductor",
    "enrichkegg", "enrichgo", "gsego", "gsekegg", "mkegg", "reactome",
    "cellranger", "kallisto", "featurecounts", "samtools", "bcftools",
    "plink", "msigdb", "uniprot", "refseq", "ncbi", "entrez", "mirbase",
    "kegg", "ensembl", "genbank", "tcga", "gtex",
    "gwas", "mendelian", "多效性", "孟德尔", "qtl", "snv", "indel",
    "polygenic", "allele", "等位基因", "hla", "连锁不平衡",
    # 生信 ID 形态（用小写片段匹配，故不写全大写的规范形式）
    "ensg", "ensmusg", "ensrnog", "ensdarg", "fbgn", "wbgene",
    "hsa_", "mmu_", "rno_", "wp0", "go:",
    # 数据格式与组学术语
    "fastq", "fasta", "vcf", "bam ", "gtf", "gff", "counts matrix",
    "rna-seq", "scrna", "atac-seq", "chip-seq",
    "转录组", "单细胞", "差异表达", "富集分析", "测序", "表达矩阵",
    "基因", "蛋白", "通路", "样本分组",
    "logfc", "fold change", "padj", "batch effect", "differential expression",
    "enrichment", "pathway", "transcriptom", "genom", "phenotyp",
]


def is_bio_relevant(text_lower):
    """文件是否涉及生物医学实体。判否 → 跳过（不产出 pass，也不算 fail）。

    维护约定：**只加信号，不删信号**。漏判（才）会静默放过；
    多判最坏只是多几条可人工忽略的提示。新增信号请一并想清楚
    它在普通工程文档里的误命中面。
    """
    return any(sig in text_lower for sig in BIO_SIGNALS)


def guess_kind(path, hint):
    if hint != "auto":
        return hint
    ext = os.path.splitext(path)[1].lower()
    return SCAN_EXT.get(ext, "report")


def read_text(path):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read(MAX_FILE_BYTES)
    except OSError as e:
        err("读取失败 %s: %s" % (path, e))
        return None


def is_excluded(rel, fn, excludes):
    """判断 rel 是否命中排除规则。

    三档匹配，从窄到宽：
      1. fnmatch(rel, pat) —— 支持 `references/*.md` 这类 glob
      2. fnmatch(fn, pat)  —— 支持 `*.tmp` 这类纯文件名
      3. 目录前缀 —— 支持直接写目录名 `references` / `references/`

    第 3 档是后补的：此前只写目录名时 fnmatch 一条都匹配不上，
    "排除了"和"没排除"看起来一模一样（静默失效），
    用户会拿到一屏假红却不知道排除根本没生效。
    """
    for pat in excludes:
        if fnmatch.fnmatch(rel, pat) or fnmatch.fnmatch(fn, pat):
            return True
        d = pat.rstrip("/")
        if d and (rel == d or rel.startswith(d + "/")):
            return True
    return False


def walk_root(root, excludes=()):
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".")]
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root).replace(os.sep, "/")
            if is_excluded(rel, fn, excludes):
                continue
            ext = os.path.splitext(fn)[1].lower()
            if ext in SCAN_EXT:
                out.append(full)
            if len(out) >= MAX_TARGETS:
                return out
    return out


def main(argv=None):
    _force_utf8()
    argv = list(sys.argv[1:] if argv is None else argv)

    parser = ArgParser(
        prog="bio_guard.py",
        description="生物医学分析声明核查（物种 / ID / 口径 / 外推边界）",
    )
    parser.add_argument("--file", action="append", default=[],
                        help="待检查文件（可重复）")
    parser.add_argument("--root", help="扫描目录（递归，跳过 .git/node_modules 等）")
    parser.add_argument("--exclude", action="append", default=[],
                        metavar="GLOB",
                        help="扫描时排除的路径（可重复；只对 --root 生效）。"
                             "支持 glob（如 references/*.md），也支持直接写目录名"
                             "（如 references，含其下全部文件）。"
                             "**教学 / 规范类文档必须排除**：它们成篇都是故意写错的示例，"
                             "扫了只会得到一屏假红，反而把真问题淹掉")
    parser.add_argument("--kind", choices=["auto", "report", "script"], default="auto",
                        help="文件类型；auto 按扩展名推断")
    parser.add_argument("--no-relevance-gate", action="store_true",
                        help="关闭相关性门，对所有目标强制跑检查。默认只查涉及"
                             "生物医学实体的文件：对普通工程脚本跑生信检查时，"
                             "EXIT_OK / MIT / SPDX 这类标识符会被误判成基因符号，"
                             "几十条假红把真问题全淹掉")
    parser.add_argument("--only", help="只跑指定检查器，逗号分隔：" + ",".join(CHECK_NAMES))
    parser.add_argument("--offline", action="store_true", help="跳过需要联网的项")
    parser.add_argument("--strict", action="store_true",
                        help="严格模式：需人工确认项也按失败计")
    parser.add_argument("--list-numbers", action="store_true",
                        help="输出数值声明清单，便于逐条接地核对")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args(argv)

    only = None
    if args.only:
        only = [x.strip() for x in args.only.split(",") if x.strip()]
        bad = [x for x in only if x not in CHECK_NAMES]
        if bad:
            err("未知检查器：%s；可用：%s" % (", ".join(bad), ", ".join(CHECK_NAMES)))
            return EXIT_USAGE

    # 收集目标
    targets = []
    for f in args.file:
        if not os.path.isfile(f):
            err("文件不存在：%s" % f)
            return EXIT_USAGE
        targets.append(f)
    if args.root:
        if not os.path.isdir(args.root):
            err("目录不存在：%s" % args.root)
            return EXIT_USAGE
        targets.extend(walk_root(args.root, args.exclude))
    if not targets:
        err("没有待检查目标：至少给 --file 或 --root")
        return EXIT_USAGE

    cfg = {
        "offline": args.offline,
        "strict": args.strict,
        "list_numbers": args.list_numbers,
    }

    results = []
    scanned = []
    skipped = []
    # 相关性门默认对所有目标生效（含 --file）：
    # 对一份没有生物医学内容的文件跑生信检查，答案是"不适用"而不是"通过"，
    # 报出来只会是噪音。两个例外：
    #   --no-relevance-gate  显式要求全查
    #   --only <检查器>      用户已明确指定查什么，不再替他判断相关性
    gate_on = not args.no_relevance_gate and not only
    for path in targets:
        text = read_text(path)
        if text is None:
            continue
        if gate_on and not is_bio_relevant(text.lower()):
            skipped.append(path)
            continue
        scanned.append(path)
        kind = guess_kind(path, args.kind)
        for name, fn, _desc in CHECKS:
            if only and name not in only:
                continue
            try:
                items = fn(path, text, kind, cfg) or []
                for it in items:
                    it["kind"] = name   # 回填检查器名，见 r() 的说明
                results.extend(items)
            except Exception as e:  # noqa: BLE001
                # 检查器自身出错 → 记为未验证（fail-closed），绝不当通过
                results.append(make_result(name, path, UNVERIFIED,
                                           "检查器异常：%s: %s" % (type(e).__name__, e)))

    if args.strict:
        for item in results:
            if item.get("status") == UNVERIFIED:
                item["status"] = FAIL
                item["detail"] = "[strict] " + str(item.get("detail", ""))

    summary = summarize(results)
    code = exit_code_for(results)
    # 一个文件都没扫到（全被相关性门滤掉）→ 不许报"通过"。
    # 没查过 != 没问题 —— 这是本套件最基本的 fail-closed 纪律。
    if not scanned and skipped:
        code = EXIT_UNVERIFIED

    doc = {
        "mode": "bio",
        "scanned": scanned,
        "skipped_irrelevant": skipped,
        "checks_run": (only or CHECK_NAMES),
        "summary": summary,
        "results": results,
    }

    human = []
    for item in results:
        human.append("%s %s: %s" % (
            status_symbol(item["status"]),
            item.get("kind", "?"),
            str(item.get("detail", ""))[:160],
        ))
        if item.get("evidence"):
            human.append("           ↳ %s" % str(item["evidence"])[:160])
    human.append("")
    if skipped:
        human.append("相关性门跳过 %d 个非生物医学文件（要全查加 --no-relevance-gate）"
                     % len(skipped))
    if not scanned and skipped:
        human.append(">>> 没有扫到任何生物医学文件：本次**未做核查**，"
                     "记为未验证，不能当通过。")
    human.append("扫描 %d 个文件 ｜ 总 %d ｜ 通过 %d ｜ 失败 %d ｜ 待确认 %d" % (
        len(scanned), summary["total"], summary["pass"], summary["fail"],
        summary["unverified"]))

    emit(doc, as_json=args.json, human_lines=human)
    return code


if __name__ == "__main__":
    sys.exit(main())
