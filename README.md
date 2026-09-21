# Touchstone · 反幻觉工程套件

> **试金石** —— 一块用来检验真金的黑色燧石。
> 它自己不产黄金，也不"相信"任何一块金属；它只是那个**让真伪显形的标准**。

[English](README.en.md) | 简体中文

[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.8+](https://img.shields.io/badge/python-3.8%2B-blue.svg)](https://www.python.org/)
[![CI](https://github.com/cndoin/touchstone/actions/workflows/ci.yml/badge.svg)](https://github.com/cndoin/touchstone/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/cndoin/touchstone)](https://github.com/cndoin/touchstone/releases)
![Zero dependencies](https://img.shields.io/badge/dependencies-0-brightgreen.svg)

MIT · Python 3.8+ · **零第三方依赖** · 离线可用

**幻觉不是"说错了"，是"没资格确定却一口咬定"。** 目标不是让输出 100% 正确（OpenAI 已从统计上证否），而是四条：

1. 每条事实性声明**可溯源** —— 有源就说，无源就删
2. 不确定必须**降级** —— 不许伪装确定
3. **没做的事不许说做了** —— 执行声明同等待遇
4. **大项目里 "我记得" 一律无效** —— 先读真实现状，再开口

---

## 什么时候**不要**用（v4.1 入场门）

**这个套件不是默认开启的。** 它是一套重型流程（8 步 + 隔离验证 + 脚本闸门），
套在小任务上只会**拖慢速度、烧掉 token**，换不来任何正确性收益。

**四问清单 —— 任一为「是」才入场；四条全为「是」就不加载，直接答：**

| # | 问 | 「是」的样子 |
|---|---|---|
| **G1** | 改动是否 **≤1 个文件**、答案是单点、无需外部资料？ | 改配置项、调 CSS、重命名变量、解释代码、单文件小重构 |
| **G2** | 是否**完全不涉及**外部可判定事实？（URL · DOI · 论文 · 法条 · API · 版本 · 包名 · 路径 · 命令输出） | 写创意文案、闲聊、格式调整 |
| **G3** | 是否**可逆**、不进版本库历史、不与既有决策冲突？ | 本地草稿、临时脚本、试验性改动 |
| **G4** | 是否**不对外发布**、不进入他人决策链？ | 内部备忘、自用工具、探索性提问 |

**四条全「是」→ 浅模式：不加载套件，直接答。**

不加载 ≠ 没底线。这两条永远生效（是习惯，不是流程）：
**① 红线不越**（不编造 URL/DOI/API/版本号/包名）；
**② 不确定就降级**（说"我不确定"是正确行为）。

**必须升级为入场的（哪怕任务看起来很小）**：用户点名要核实 · 输出会被直接采用或对外发布 ·
不可逆操作 · 用户先表态而你要附和 · 你发现自己想说"应该是/一般来说"。

---

## 数学模式（v4.2：数值结论不许心算）

**数学幻觉跟一般事实幻觉不一样——它至少一半是可判定的。** 算术对不对、证明合不合法，
机器能验。所以这一半能做到接近零；但错误藏在不同层次，**治法互不通用**。

| 层 | 症状 | 治法 | 现状 |
|---|---|---|---|
| ① 算术 / 符号算错 | `3×7=20`、移项漏变号 | **强制确定性引擎**（Python / SymPy / Z3） | 已解决 |
| ② **可执行但未接地** | 公式对、量纲对，**变量代错** | **双层校验**：符号有效性 + 语义接地 | 研究前沿 |
| ③ 题目病态 / 缺条件 | 少一个条件、自相矛盾、超定义域 | **拒答 / 澄清闸门**（答之前先判） | **最难** |
| ④ 验证器本身不可信 | 规则式漏判等价格式；模型式被刷分 | **去锚定**：裁判先自立作答 | 有明确解法 |

**四条硬条款：**

1. **数值结论必须有执行记录** —— 来自实跑的 `python3 -c "…"` 或 SymPy，不许来自"我认为"。
2. **工具成功 ≠ 算对了**。跑通只证明语法对；第二层必须问
   **「这个变量指题面里的哪个词？」** —— 指不出来就是未接地，降级。
3. **答题前判条件是否齐**：缺 ⟹ 先追问；不可追问则**条件化**（「若 X=… 则…」）；最后才纯拒答。
   **禁止自己假设一个数填进去**。
4. **核对答案时裁判先自立作答**（铁律 2 的数学形态）。顺序反了整条链归零：
   先看候选会把假阳性从 0.012 推回 0.719。

> ⚠️ 第③层**不随模型变强而变好，也不随"多想一会儿"变好**——
> Soohak 的拒绝子集上**没有任何模型超过 50%**（arXiv 2605.09063）。
> 所以别用"再仔细检查一遍"当闸门。详见 `references/18-math-mode.md`。

---

## 快速开始

在 `touchstone/` 目录下执行（Windows 把 `python3` 换成 `python`）。

```bash
# 0) 模型能力分档：不同强度的模型用不同核查策略
python3 scripts/model_profile.py --model claude-opus-4  --net on
python3 scripts/model_profile.py --model gpt-4o-mini    --net off --json

# 1) 硬核查：URL / DOI / 文件 / 命令 / 包版本（查不到 = 不成立）
python3 scripts/hardcheck.py --file ./README.md --cmd "git status --porcelain" --offline

# 2) 交付前闸门（非零退出码 = 不许交付）
python3 scripts/claim_lint.py --input examples/claims-good.json

# 3) 依赖与符号幻觉防护（幻影 import / 包幻觉 / slopsquatting）
python3 scripts/dep_guard.py --root . --offline --strict

# 4) 大项目账本：记决策 / 查漂移
python3 scripts/ledger.py add --kind decision --subject "DI 框架" --value "Hilt" \
    --source "docs/arch.md#3" --verify-file app/build.gradle.kts --verify-pattern hilt
python3 scripts/ledger.py check --root . --drift

# 5) 一键跑完整条链：hardcheck → dep_guard → claim_lint
python3 scripts/pipeline.py --root . \
    --checks .touchstone/checks.json \
    --claims .touchstone/claims.json --level L1

# 6) 一致性统计（无原文、不可检索时的兜底）
python3 scripts/selfcheck.py --samples examples/samples.json

# 7) 回归集
python3 scripts/regression.py --cases assets/regression-cases.json

# 8) 快速自检（72 条，秒级；每次改动后跑）
python3 scripts/selftest.py

# 9) 深度健壮性测试（70 条；发版前 / 换环境后跑）
python3 scripts/robustness_test.py

# 10) 工程一致性 / 稳定性测试（99 条；发版前跑）
python3 scripts/stability_test.py
```

> **第一次跑，退出码可能不是 0 —— 这不一定是出错**，先看下表再判断：
>
> | 命令 | 常见非零退出码 | 含义 |
> |---|---|---|
> | `selfcheck.py` | **2** | 灰区（自洽度处于中间带）。这是**路由信号**，提示"该去定向检索或隔离验证了"，不是失败 |
> | `hardcheck.py --offline` | **2** | 离线时外部 URL/包只能记为"未验证"。**未验证 ≠ 通过**，也 ≠ 失败 |
> | `dep_guard.py --offline` | **2** | 同上：离线无法查 registry，外部包记为 UNVERIFIED |
> | `claim_lint.py` | **1 / 2** | 1 = 真的没通过（不许交付）；2 = 有未验证项 |
>
> 完整语义见下方「退出码约定」。**有疑义时把 2 当作"需要人去核实"，不要当成"通过"。**

### 模型适配（不同强度的模型，打法不同）

| 档 | 代表 | 自我核查可信? | 打法 |
|---|---|---|---|
| S/A | 前沿旗舰 / 主力 | ✅ | CoVe 隔离验证 + 原生引用可用，外部硬核查兜底 |
| B | 轻量/中端 | ❌ | **不依赖自我核查**：全部走外部脚本 + 强制引用 + 缩短单次输出 |
| C | 小模型/边缘 | ❌ | 只做可判定项核查（存在性），禁止开放式事实结论 |

**为什么**：CoVe、自一致性的前提是"模型知道自己不知道"。弱模型没有这个元认知——
让它"再检查一遍"，结果是**把错误答案再确认一遍**。所以：**模型越强越能让模型自查，越弱越要把判断权交给脚本。**

详见 `references/16-model-adaptation.md`（OpenAI / Anthropic / Google / DeepSeek 官方机制，已回溯一手来源）。

### 诱导型幻觉（v3.4：与模型强弱无关）

有一类幻觉，**模型知道正确答案，却因为用户先表态而改口**。它不是"不知道"，所以前三层防御都拦不住。

- 一手：*Science* 391(6792) DOI 10.1126/science.aec8352 —— 11 个模型比人类多肯定用户行为 **49%**
- 一手：arXiv 2602.19141 —— **告知用户"模型可能谄媚"无效**；"事实型谄媚者"（只做选择性强调）
  造成的后果比编造型更严重
- 一手：arXiv 2607.11414 —— **在 FinQA 上，8/8 采样全部一致的答案里仍有 15–23% 是错的**
  （金融 QA 基准，Qwen3-8B / Llama-3.1-8B / Gemma-2-9B；这是限定域结论，不要外推成通用规律）

对应铁律 9：**核查前把待验问题中性重述，用户的立场不得进入证据链。**
模板与完整对照见 `references/17-vendor-and-induction.md`。

---

### 三套测试的分工

| | `selftest.py` | `robustness_test.py` | `stability_test.py` |
|---|---|---|---|
| 定位 | 快速冒烟 | 深度健壮性 | 工程一致性 |
| 用例 | 72 条 | 70 条 | 99 条（`--no-install-check` 时 97 条） |
| 覆盖 | 正常路径 + 关键失败路径 | 边界 / 异常 / 编码 / 并发 / 性能 / 幂等 / 极端参数 | 编译 / 幂等 / 并发写 / 垃圾输入 fuzz / 环境（GBK·离线·只读·非 ASCII 路径）/ 文档与版本一致性 / 资产合法性 / 安装目录同步 |
| 耗时 | 秒级 | 几十秒 | 几分钟（含 16 路并发与 200KB 级输入） |
| 何时跑 | 每次改动后 | 发版前、换环境后 | 发版前（尤其动过 hook、文档或版本号后） |

> `stability_test.py` 的 G 组会拿工作区与安装目录逐字节比对，**必须本地装过这个 skill 才有意义**。
> 所以在 CI 或干净 clone 里跑时会自动降级为 97 条（G 组跳过）——
> 想显式跳过加 `--no-install-check`；安装目录不在默认位置时设
> `TOUCHSTONE_INSTALLED=/path/to/skill`。
> **99 条是本地完整模式的数字，97 条不是"少了测试"。**

前两套回答"脚本能不能跑对"，第三套回答"**整个技能包有没有烂掉**"——
某个 hook 被改出语法错误、文档写的版本号和 `VERSION` 文件不一致、
文档引用的文件其实不存在、工作区改了没同步到安装目录，都会被它抓出来。

**robustness 的核心断言不是"结果对不对"，而是**：绝不出现 Traceback、退出码必须落在 {0,1,2,3}、
`--json` 输出必须可解析、重复执行结果一致、批量场景在耗时预算内。

**零依赖**：只用 Python 标准库（3.8+），Windows / Unix 双兼容，离线可用（`--offline`）。
**效率**：网络核查带 6 小时缓存、默认 4 并发、瞬时故障自动重试、可设核查预算上限。
**稳定**：fail-closed + 明确降级；hook 脚本解析失败一律放行，不会因脚本 bug 卡住工作。

---

## 目录结构

```
touchstone/
├── SKILL.md                      主入口：铁律 / 红线 / 8 步工作流 / 风险分级 / 闸门
├── README.md / README.en.md      中文 / 英文说明
├── VERSION                       版本号（六处一致的唯一事实来源，见 RELEASE.md）
├── LICENSE                       MIT
├── NOTICE                        归属、第三方声明、无担保条款
├── ATTRIBUTIONS.md               借鉴项目与论文的出处、License、一手/二手标注
├── CHANGELOG.md                  版本变更（Keep a Changelog 格式）
├── CITATION.cff                  学术引用元数据（CFF 1.2.0）
├── CONTRIBUTING.md               贡献指南 + 三套测试怎么写
├── CODE_OF_CONDUCT.md            行为准则（含「编造事实」特别条款）
├── SECURITY.md                   安全政策与私有漏洞报告渠道
├── RELEASE.md                    发版流程与检查清单
├── MAINTAINERS.md                维护者与决策机制
├── .editorconfig                 统一编码 / 换行 / 缩进
├── .github/                       CI、issue / PR 模板、元数据校验脚本
├── i18n/en/SKILL.md              英文主入口
├── references/                   17 篇深度参考（按需读，不要一次全读）
│   ├── 01-core-doctrine.md       幻觉为什么必然存在，我们能做什么
│   ├── 02-context-settings.md    M1 三种上下文设定
│   ├── 03-hard-checks.md         M3 可判定项逐项查法 + 脚本参数
│   ├── 04-verification-workflow.md  M4 八步流程 + 隔离验证模板
│   ├── 05-claim-labels.md        M5 五标签 + 置信度 + 话术
│   ├── 06-cost-routing.md        检测器选型 + ADR 成本路由
│   ├── 07-large-project.md       大项目：账本 / 漂移 / 跨会话 / 子 agent
│   ├── 08-code-mode.md           编码专项：幻影 API / 版本 / 编译验证
│   ├── 09-anti-patterns.md       反模式 + 交付前自检表
│   ├── 10-metrics-regression.md  度量指标 + 回归集
│   ├── 11-harness-adapters.md    Claude Code / DeepSeek / 通用 harness
│   ├── 12-uncertainty-calibration.md  语义熵 / 自一致性 / 置信度校准
│   ├── 13-frontier-2026.md       2026 前沿论文与开源生态（含可信度分档）
│   ├── 14-supply-chain-code.md   包幻觉 / slopsquatting 防护
│   ├── 15-stability-performance.md  特殊环境稳定性、缓存/并发/预算、防崩溃纪律
│   ├── 16-model-adaptation.md    模型分档：强模型自查 vs 弱模型全走脚本
│   ├── 17-vendor-and-induction.md  厂商官方机制 + 诱导型 / 谄媚型幻觉
│   └── _deprecated-v1/           v1 旧稿，仅留档，不参与当前流程
├── scripts/                      可执行闸门（纯标准库，14 个）
│   ├── _common.py                公共工具（fail-closed 语义、退出码约定）
│   ├── hardcheck.py              URL / DOI / 文件 / 命令 / PyPI / npm
│   ├── claim_lint.py             输出契约闸门（逻辑一致性，不只是格式）
│   ├── ledger.py                 项目账本（add / get / list / check / remove）
│   ├── selfcheck.py              采样一致性统计
│   ├── regression.py             回归集
│   ├── dep_guard.py              依赖与符号幻觉防护（幻影 import / 包幻觉 / slopsquatting）
│   ├── model_profile.py          模型能力分档 → 核查策略推荐（适配强弱模型）
│   ├── verifiers.py              可插拔检测器桥接（外部检测器探测）
│   ├── pipeline.py               一键编排：hardcheck → dep_guard → claim_lint
│   ├── audit.py                  开源合规审计（许可证头 / 零依赖 / 隐私 / 版本一致）
│   ├── selftest.py               快速自检（72 条，秒级）
│   ├── robustness_test.py        深度健壮性测试（70 条：边界/异常/并发/性能/幂等）
│   └── stability_test.py         工程一致性测试（99 条：编译/幂等/并发/fuzz/环境/文档一致/安装同步）
├── assets/
│   ├── claim-schema.json         输出契约 JSON Schema
│   ├── ledger-schema.json        账本 JSON Schema
│   ├── regression-cases.json     回归集模板
│   ├── ci/github-actions.yml     CI 闸门示例（给使用方抄的）
│   └── templates/                claims / checks / 子 agent 核查模板
├── examples/                     可直接跑的示例（含一个故意做错的）
└── adapters/
    ├── claude-code/              settings-hooks.json + hooks/
    │   └── hooks/                verify_gate / subagent_gate / precompact_snapshot / guard_bash
    ├── deepseek/                 系统提示 + 推理模型处理 + 中文规则
    └── generic/                  Codex / Cursor / Cline / Roo / 自研 接入
```

---

## 安装

### 1. 拿到代码

```bash
# 方式 A：git clone（推荐，方便跟随升级）
git clone https://github.com/cndoin/touchstone.git
cd touchstone

# 方式 B：下载发行包
#   https://github.com/cndoin/touchstone/releases → touchstone-vX.Y.Z.zip
```

无需安装任何依赖 —— 只用 Python 标准库（3.8+），Windows / macOS / Linux 都能直接跑。

装完先验证一次：

```bash
python scripts/selftest.py     # Windows 用 python；应输出 38/38 通过
```

> Windows 用户注意：脚本已强制 UTF-8 输出，但**建议在 PowerShell 里先执行
> `$env:PYTHONUTF8="1"`**，避免极少数终端下中文仍显示为乱码。

### 2. 放进你的 agent

#### WorkBuddy / 通用 skill 目录

```bash
cp -r touchstone ~/.workbuddy/skills/
```

#### Claude Code（推荐，强制力最强）

```bash
cp -r touchstone .claude/skills/            # 项目级
cp -r touchstone ~/.claude/skills/          # 用户级
# 再合并 adapters/claude-code/settings-hooks.json 到 settings.json
```

合并完**务必手动触发一次** hook 验证：hook 解析失败时会静默放行（这是刻意设计，
不让工具 bug 卡住你的工作），所以配置错误不会有任何报错提示。

#### 其他 harness

见 `adapters/generic/README.md`（AGENTS.md / .cursorrules / .clinerules 等放置位置）。

---

## 核心机制（八层）

| 层 | 机制 | 来源 |
|---|---|---|
| **M0** | **入场门（先判要不要启用，小任务零成本绕过）** | 本套件自研（v4.1） |
| M1 | 上下文判定器（Accurate / Noisy / Zero） | RefChecker |
| M2 | 行为基线（逃逸通道 + 红线 + 语气对齐） | Anthropic 官方 + OpenAI 2509.04664 + ICML 2605.01428 |
| M3 | 硬核查器（可判定项先啃） | 微软 refchecker + FacTool |
| M4 | 核查工作流（八步 + 隔离验证） | FacTool + CoVe |
| M5 | 标签 / 置信度 / 反例解释 | verify-gate + Cleanlab TLM |
| M6 | 成本路由（便宜先跑，灰区才升级） | HalluScan ADR |
| **M7** | **数学模式（数值强制确定性引擎 + 语义接地 + 病态题闸门）** | **本套件自研（v4.2）；理论来自 Neuro-symbolic PRM 2608.26329 / Soohak 2605.09063 / 2607.05904** |

**v2 新增的两层**：**大项目机制**（账本 + 漂移检测 + 子 agent 不采信）和**可执行闸门**（脚本化，fail-closed）。

---

## 风险分级

| 级别 | 场景 | 投入 |
|---|---|---|
| L0 | 闲聊、创意、内部草稿、单文件小改 | 行为基线 + 红线；**不加载本套件**（入场门全「是」） |
| L1 | 业务咨询、写代码、写报告 | + 硬核查 + 八步工作流 |
| **L1+** | **含会被采用的数值/符号结论**（财务、统计、工程参数、公式推导） | **+ 数学模式**：确定性引擎执行记录 + 语义接地 + 条件齐备性 |
| L2 | 法律 / 医疗 / 金融 / 对外发布 / 不可逆操作 | + 强制检索 + 多模型交叉 + 人工闸门 |

---

## 退出码约定（脚本统一）

| 退出码 | 含义 |
|---|---|
| 0 | 通过 |
| 1 | 存在失败（**不许交付**） |
| 2 | 存在未验证（网络失败等）—— **未验证 ≠ 通过** |
| 3 | 用法/输入错误（含参数写错，argparse 错误已统一到 3，不会与"未验证"混淆） |

`selfcheck.py` 的退出码是**路由信号**而非错误：0=高一致，2=灰区，**4=低一致**；输入错误仍为 3。
（低一致用 4 而不是 3，就是为了不占用"错误"的语义。）

---

## 度量（不然不知道有没有用）

| 指标 | 目标 |
|---|---|
| 无源声明率 | → 0 |
| 执行声明未验证率 | → 0 |
| 引用可解析率 | → 100% |
| 弃权率 | 5–20%（太低 = 在硬猜） |

详见 `references/10-metrics-regression.md`。

---

## 名字由来

**Touchstone（试金石）** 是一种黑色燧石：把金属在上面划一道，看留下的条痕颜色就能判断成色。

这个意象正好是本套件的立场：

- **它不替模型判断对错。** 让模型"再检查一遍"，在弱模型上是有害的
  （arXiv 2601.00513，d = −0.14 ~ −0.33）—— 自我核查不是可靠的裁判。
  详见 `references/16-model-adaptation.md`。
- **它只提供可执行的判定标准。** 查得到就有源，查不到就不成立；
  能由机器判定的一律写成脚本，不写成"请注意核实"这类句子。
- **判不了就标记 `unverified`。** 未验证 ≠ 通过。这一点是整套机制的底线。

> **曾用名 `dehallucination`。** 改名是为了好读好记；
> 但 `dehallucination` 仍作为关键词保留在文档与搜索别名里，
> 搜旧名字、用旧链接都能找到这里。GitHub 仓库重命名后旧 URL 会自动跳转。

---

## 参与项目

| 你要做什么 | 看这里 |
|---|---|
| 提 bug / 建议功能 | GitHub Issues（有模板，**别开空白 issue**） |
| 提 PR | `CONTRIBUTING.md` + PR 模板（**必须贴验证证据**） |
| 报安全漏洞 | `SECURITY.md` → GitHub Security Advisory（**私有，别开 issue**） |
| 学术引用 | `CITATION.cff`（GitHub 侧边栏 "Cite this repository" 可直接取用） |
| 行为准则 | `CODE_OF_CONDUCT.md` |
| 发版 | `RELEASE.md` |
| 找人 | `MAINTAINERS.md` |

> **对贡献者多一条要求**：本仓库的文档不许出现编造的数字、编造的论文编号、
> 被外推的结论。每个数字都要有出处，二手来源必须标注。
> 这条写进了 `CODE_OF_CONDUCT.md` —— 一个反幻觉仓库如果自己容忍幻觉，它就没有价值。

---

## 免责

本套件**降低**幻觉风险，不消除风险。高风险场景（法律/医疗/金融/不可逆操作）必须保留人工复核。
