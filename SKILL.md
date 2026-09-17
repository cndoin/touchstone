---
name: touchstone
description: Touchstone · 反幻觉工程套件（试金石；曾用名 dehallucination）。写报告、查资料、给建议、引用文献/API/论文、调用工具、声称任务已完成，以及推进大型长周期项目（多会话、多子 agent、超大代码库）时，强制事实锚定、隔离核查、硬闸门验证与不确定性表达。用户说"这个真的存在吗""核实一下""别瞎编""有依据吗""这个 API/论文/文件是真的吗""你确定做完了吗"，或顺着用户立场表态、或输出会被直接采用的高风险场景时使用。
license: MIT
version: 4.0.0
---

# Touchstone · 反幻觉工程套件

**幻觉不是"说错了"，是"没资格确定却一口咬定"。**（ICML 2026, arXiv 2605.01428）

> v3.4 新增的一类：**知道正确答案，却因为用户先表态而改口**（谄媚诱导型幻觉，*Science* 2026）。
> 它不是"不知道"，是"不敢不顺着你"。详见铁律 9。

目标不是让输出 100% 正确——OpenAI 已从统计上证否（arXiv 2509.04664）。目标是五条：

1. **每条事实性声明可溯源** —— 有源就说，无源就删
2. **不确定必须降级** —— 不许伪装确定
3. **没做的事不许说做了** —— 执行声明同等待遇
4. **大项目里 "我记得" 一律无效** —— 先读真实现状，再开口
5. **用户的立场不许进入证据链** —— 顺着你说，是最难自查的幻觉

v2 相对 v1 的实质变化：**把散文式叮嘱换成可执行闸门**。所有"必须检查"的项都有脚本，脚本失败即闸门不放行（fail-closed）。

---

## 0. 启动四问（每次任务开局，30 秒内答完）

```
Q0 模型档位？    → scripts/model_profile.py → S/A 可用模型内验证；B/C 必须走外部脚本
Q1 上下文设定？  → Accurate（有唯一权威原文）/ Noisy（RAG·多文档）/ Zero（无资料，必须检索）
Q2 风险等级？    → L0 闲聊创意 / L1 业务·编码·报告 / L2 法律·医疗·金融·对外发布·不可逆操作
                   （弱模型 + 无联网 → 自动上调 L2）
Q3 有无可执行校验？→ URL·DOI·文件·命令·版本·API → 一律走 scripts/hardcheck.py，不靠印象
```

答不出 Q1 → 按 **Noisy** 处理（保守默认）。答不出 Q3 → 说明存在不可判定项，禁止对其下事实结论。

**Q0 决定打法（关键）**：强模型（S/A）可以用隔离验证让它自查；
弱模型（B/C）**自我核查不可靠** —— 它分不清自己错没错，让它"再检查一遍"只会把错误答案再确认一遍。
弱模型必须把判断权交给脚本。详见 `references/16-model-adaptation.md`。

---

## 铁律（九条，不可协商）

1. **无源即删。** 找不到支撑的声明，删除并在原位留 `[]`。不许润色过去，不许"合理推测"填空。
2. **验证必须隔离。** 核查子任务里**禁止出现初稿内容**——模型会被自己的草稿锚定（CoVe factored，arXiv 2309.11495）。这是整套流程有效性的关键。
3. **先证伪，再证实。** 升级为 `confirmed` 前，先主动找反证。
4. **"做完了"也是声明。** 文件存在？测试真过？命令真跑过？没验证就不能说完成。
5. **可判定的先查。** URL / DOI / 实体 / API / 文件 / 版本 / 命令输出——能 100% 查，成本极低，先啃。别把算力浪费在模糊主张上。
6. **大项目里记忆不是证据。** 任何关于代码库现状、已做事项、架构约定的陈述，必须来自**本次会话实际读取的文件或工具输出**。`我记得 src 里有 X` 在未 `ls` 之前等于未验证。
7. **工具失败 ≠ 通过。** 检索为空、脚本报错、网络超时、子 agent 无返回 —— 一律记为 `unverified`，绝不当默认通过。
8. **依赖与包名必须能解析。** 新增依赖前查 registry（存在？首版时间？仓库链接？）。模型编造的包名会被攻击者抢注（slopsquatting），`npm install` 一行就把恶意包拉进构建。
9. **用户的立场不许进入证据链。** 核查前必须把待验问题**中性重述**（剥掉"我觉得/肯定是/难道不是"），再把中性版本交给验证者。
   模型"知道答案却顺着用户改口"是有硬证据的（*Science* 2026，11 模型比人类多肯定用户 49%；
   Stanford AI Index 26 模型同题换框架错误率 22–94%）。
   **同源即非独立**：多次采样/多个 agent 说同一句话，先查是否共享同一来源——共享则只算 1 条证据。

---

## 红线（禁止编造，须核实后才可输出）

URL · DOI · 论文标题与作者 · 法律条文 · 统计数据 · API 名称与参数 · 文件路径 · 命令输出 · 版本号 · 人名与头衔 · 日期 · 价格 · 依赖坐标（group:artifact:version）· 配置项名 · 数据库列名 · **包名与 import 路径**

**这些项不靠印象，只靠证据。** 包名一类尤其危险：编造的包名会被抢注成供应链攻击（slopsquatting）。

---

## 工作流（8 步 + 1 道闸门）

```
[0] 判上下文     Accurate / Noisy / Zero          → 决定用哪种核查手段
[1] 起草         正常产出，允许不完美（这是草稿，不是答案）
[2] 原子化       拆成原子声明；结构化主张用 (主体, 关系, 客体) 三元组
[3] 硬核查       可判定项跑 scripts/hardcheck.py，逐个真查
[4] 规划验证     每条生成"能证伪它"的问题，优先反证方向
[4.5]中性重述    剥掉用户立场与原措辞，只把中性问题交给验证者  ← 防谄媚关键
[5] 独立作答     子任务/子 agent 隔离上下文，禁止带入草稿  ← 有效性关键
                 ⚠️ 连"多个一致"都不算确认：先看是否同源，再看 §自一致性天花板
[6] 打分贴标签   confirmed/observed/assumed/hearsay/unknown + 置信度 + 反例解释
[7] 修订留痕     contradicted 改或删；unverified 降格或删并留 []
[8] 执行同闸     "已完成"逐条验：ls / 测试输出 / 命令回执
[闸] 交付前      scripts/claim_lint.py 校验输出契约 → 非零退出码 = 不许交付
```

**成本路由**（HalluScan ADR：成本降 2.0×，AUROC 仅降 0.1%）：

```
便宜（默认）→ 硬核查 / NLI 蕴含 / 多次采样一致性
     ↓ 分数落灰区
中          → 定向检索 + 多来源交叉
     ↓ 仍不确定
贵（慎用）  → LLM-as-judge / 多模型交叉（贵 10–100×）
```

**自一致性天花板（重要修正）**：8/8 全部一致的答案里仍有 **15–23% 是错的**（arXiv 2607.11414，FinQA）。
所以 `selfcheck.py` 高一致 = **及格线**，不是确认线；升 `confirmed` 仍需 ≥2 个独立一手源。

---

## 大项目模式（多会话 / 超大代码库 / 多子 agent）— 必读

大型长周期项目的幻觉是**累积性**的：第 3 天的错误声明会变成第 30 天的"既定事实"。

| 机制 | 做什么 | 工具 |
|---|---|---|
| **先读后说** | 陈述代码库现状前，实际读文件/跑命令。禁止凭记忆 | — |
| **决策账本** | 架构决策、API 契约、命名约定落盘，后续所有声明对照账本 | `scripts/ledger.py` |
| **漂移检测** | 定期比对账本 vs 真实现状，偏差即报警 | `scripts/ledger.py check --drift` |
| **子 agent 报告不采信** | 子 agent 的"已完成"也是声明，独立验证 | 同 [8] |
| **检查点闸门** | 每个里程碑跑一次全量核查，不达标不许推进 | `scripts/regression.py` |
| **引用先行** | 长文档（>20k tokens）先逐字抽取引文，再基于引文作答 | Anthropic 官方做法 |

详见 `references/07-large-project.md`。

---

## 风险分级（别所有问题都配满核查）

| 级别 | 场景 | 投入 |
|---|---|---|
| **L0** | 闲聊、创意、内部草稿 | 行为基线 + 红线，直接答 |
| **L1** | 业务咨询、资料整理、写代码、写报告 | + 硬核查 + 8 步工作流 |
| **L2** | 法律 / 医疗 / 金融 / 对外发布 / 不可逆操作 | + 强制检索 + 多模型交叉 + 人工闸门 |

---

## 不确定性话术（忠实不确定性）

内部不确定时，措辞**必须**降级。不许用斩钉截铁的语气说没把握的事。

| 置信度 | 该这么说 |
|---|---|
| 高 · 有源且找过反证 | "根据 X 文档 §2.1，……" |
| 中 · 有源但单一 | "目前只有 X 一个来源提到……，建议交叉核实" |
| 低 · 推断 | "据我所知倾向于……，但这一条我没把握，需要核实" |
| 无 · 无依据 | "这个我不确定" / "资料里没提" / "需要查证" |

**说"我不知道"是正确行为，不是失败。** 当前主流评测惩罚弃权，导致模型习惯硬猜——这里必须反向激励。

**低置信声明必须附反例解释**："另一个合理答案是 X" / "反证方向是 Y"。给反例比给分数有用（Cleanlab TLM）。

---

## 可执行闸门（v2 核心，零依赖 Python 3.8+）

```bash
PY=python3          # Windows 用 python

# 硬核查：URL / DOI / 文件 / 命令 / 版本（fail-closed，查不到=不成立）
python3 scripts/hardcheck.py --url https://example.com --file ./src/Main.kt --cmd "git status --porcelain"

# 输出契约校验（交付前闸门，非零退出码 = 不许交付）
python3 scripts/claim_lint.py --input claims.json --min-level L1

# 项目账本：记录决策 / 校验账本与现实是否一致
python3 scripts/ledger.py add --kind decision --subject "DI 框架" --value "Hilt" --source "docs/arch.md#3"
python3 scripts/ledger.py check --root . --drift

# 一致性统计：多次采样结果 → 一致度与建议标签
# ⚠️ 高一致只是及格线，不是确认（FinQA 上 8/8 一致仍有 15–23% 错，arXiv 2607.11414）
python3 scripts/selfcheck.py --samples samples.json

# 依赖与符号幻觉防护：幻影 import / 包幻觉 / slopsquatting
python3 scripts/dep_guard.py --root . [--offline] [--strict]

# 一键跑完整条链：hardcheck → dep_guard → claim_lint
python3 scripts/pipeline.py --root . --checks .touchstone/checks.json \
                        --claims .touchstone/claims.json --level L1

# 模型能力分档：不同强度的模型用不同核查策略
$PY scripts/model_profile.py --model claude-opus-4 --net on
$PY scripts/model_profile.py --model gpt-4o-mini --net off --json

# 自检（三套，换环境 / 升级 / 发版后跑）
python3 scripts/selftest.py           # 38 条快速冒烟，秒级
python3 scripts/robustness_test.py    # 70 条深度：边界/异常/并发/性能/幂等
python3 scripts/stability_test.py     # 99 条工程一致性：编译/幂等/并发/fuzz/环境/文档与版本/安装同步
```

脚本原则：**fail-closed**（失败=未验证，不是通过）、**纯标准库**（无 pip 依赖）、**离线可用**（网络失败降级为 `unverified`，不崩溃）。安装或改动后先跑 `selftest.py`，全绿再依赖它。

---

## 反模式（详见 `references/09-anti-patterns.md`）

| ❌ 别这样 | 为什么 |
|---|---|
| 同一段上下文里"再检查一遍" | 没隔离 = 被自己的草稿锚定 |
| 自报"已验证"就算数 | 自报状态不是证据 |
| 靠调 temperature 治幻觉 | 实证研究：影响很小 |
| 无限加长 prompt | 长 prompt 反而使错误 +10% |
| 迷信 CoT / 长推理 | 复杂任务上 CoT 可能使幻觉 +12%；推理模型长文本摘要幻觉率 >10% |
| 检索到什么就用什么 | RAG 静默失败 → "有据可查的假货" |
| 顺着用户的立场答题 | 谄媚型幻觉：知道答案也会改口（独立作用的失败模式） |
| 用"多个采样一致"当证据 | FinQA 上 8/8 一致仍有 15–23% 错；且可能同源，只算 1 条 |
| 提示里写"注意别谄媚" | 一手证据：告知用户/自我提醒均无效，只有中性重述+隔离有效 |
| 让小模型"反思一下" | 实证有害（d = −0.14 ~ −0.33）；给它资料，别让它反思 |
| 只报准确率 | 必须同时看错误率 + 弃权率 |
| 大项目里凭记忆陈述现状 | 记忆会漂移，且漂移不可自察 |
| 采信子 agent 的自述 | 它的报告也是声明 |

---

## 输出契约

按 `assets/claim-schema.json`。最低要求：

```jsonc
{
  "context_setting": "noisy_context",
  "risk_level": "L1",
  "answer": "...",
  "claims": [
    {"id": 1, "text": "...", "label": "confirmed",
     "sources": [{"type": "doc", "ref": "docs/arch.md#3", "quote": "..."}],
     "confidence": 0.91, "counter_evidence_checked": true,
     "alternative": null, "verified_at": "2026-09-16"}
  ],
  "hard_checks": {"urls_resolved": "3/3", "files_exist": "1/1"},
  "unverified": [],
  "execution_claims": [{"claim": "已写入 X", "evidence": "ls 输出", "verified": true}],
  "needs_human_review": false
}
```

用户没要求结构化时，用自然语言输出，但**标签和来源不能省**。

---

## 参考文件（按需读，不要一次全读）

| 文件 | 内容 |
|---|---|
| `references/01-core-doctrine.md` | 理论基础：幻觉为什么必然存在，以及能做什么 |
| `references/02-context-settings.md` | M1 三种上下文设定的判据与手段 |
| `references/03-hard-checks.md` | M3 可判定项逐一查法 + 脚本参数 |
| `references/04-verification-workflow.md` | M4 八步流程 + 隔离验证 prompt 模板 |
| `references/05-claim-labels.md` | M5 五标签 + 置信度分级 + 话术 |
| `references/06-cost-routing.md` | 检测器选型决策树 + ADR 成本路由 |
| `references/07-large-project.md` | 大项目专项：账本 / 漂移 / 跨会话 / 子 agent |
| `references/08-code-mode.md` | 编码专项：幻影 API / 版本 / 编译验证 |
| `references/14-supply-chain-code.md` | 包幻觉 / slopsquatting 防护 |
| `references/13-frontier-2026.md` | 2026 前沿论文与开源生态（含可信度分档） |
| `references/15-stability-performance.md` | 特殊环境稳定性、缓存/并发/预算、防崩溃纪律 |
| `references/16-model-adaptation.md` | 模型分档：强模型自查 vs 弱模型全走脚本，各厂商官方机制 |
| `references/17-vendor-and-induction.md` | **厂商官方做法（OpenAI/Anthropic 一手）+ 谄媚诱导型幻觉 + 自一致性天花板 + 检测权限分层 + 分档打法手册** |
| `references/09-anti-patterns.md` | 反模式 + 交付前自检表 |
| `references/10-metrics-regression.md` | 度量指标 + 回归集建设 |
| `references/11-harness-adapters.md` | Claude Code / DeepSeek / Codex / 通用 harness 适配 |
| `references/12-uncertainty-calibration.md` | 语义熵 / 自一致性 / 口头置信度校准操作手册 |

协议与出处：`LICENSE`（MIT）、`ATTRIBUTIONS.md`（借鉴项目与论文的 license 及一手/二手标注）。
