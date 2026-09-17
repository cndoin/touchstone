# CHANGELOG

> 格式遵循 [Keep a Changelog](https://keepachangelog.com/)；版本号遵循 [SemVer](https://semver.org/)。
> 发版流程见 `RELEASE.md` —— 版本号在 `VERSION` / `SKILL.md` / `i18n/en/SKILL.md` /
> `CHANGELOG.md` / `CITATION.cff`（version 与 preferred-citation.version）六处必须一致。

---

## v4.0.0（2026-09-17）· 改名 Touchstone（试金石）· 破坏性变更

**MAJOR：路径与目录名变了。** 行为语义与退出码都没变，但升级后需要迁移一次。

### 为什么改名

`dehallucination` 12 个字母、像医学术语、不好念也不好记。

**Touchstone（试金石）** 是一种黑色燧石——把金属在上面划一道，看条痕颜色就能判断成色。
它自己不产黄金，也不"相信"任何一块金属，只是那个**让真伪显形的标准**。
这与本套件的立场完全一致：不替模型判断对错，只提供可执行的判定标准。
详见 README「名字由来」。

> `dehallucination` 仍作为搜索别名保留在 `SKILL.md` 的 description 与 README 里，
> 搜旧名字能找到本项目；GitHub 仓库重命名后旧 URL 会自动跳转。

### 升级必读（破坏性变更）

| 变更 | 旧 | 新 | 怎么迁 |
|---|---|---|---|
| 技能目录名 | `dehallucination/` | `touchstone/` | 重装：`cp -r touchstone ~/.workbuddy/skills/` |
| 运行时数据目录 | `.dehallucination/` | `.touchstone/` | 老项目 `mv .dehallucination .touchstone` |
| 环境变量前缀 | `DEHALLU_*` | `TOUCHSTONE_*` | **旧名继续可用**（两个都读），建议逐步切换 |

三个环境变量：`TOUCHSTONE_CACHE_DIR` / `TOUCHSTONE_INSTALLED` /
`TOUCHSTONE_ALLOW_DANGEROUS`；对应旧名 `DEHALLU_*` 兼容至下一个大版本。

**Claude Code 用户特别注意**：hook 路径写死在你自己的 settings.json 里，必须重新配一次。
配完**务必手动触发一次验证** —— hook 解析失败是静默放行的，配错不会有任何报错。

### 同步改动

- 仓库与所有 URL：`cndoin/dehallucination` → `cndoin/touchstone`
- 修复 Windows 下 `subagent_gate.py` 未将标准输入切换为 UTF-8、可能漏检中文完成断言的问题
- `SKILL.md` / `i18n/en/SKILL.md` 的 `name` 字段 → `touchstone`
- **标题去掉版本号**（`# Touchstone · 反幻觉工程套件`）—— 版本号写在标题里只会持续漂移
- `LICENSE` / `NOTICE` / `CITATION.cff` 版权行 → `Touchstone contributors`
- `stability_test.py` 临时目录前缀 `dehallu-stability-` → `touchstone-stability-`
- `.gitignore` 补 `.touchstone/`，并保留 `.dehallucination/` 便于老项目清理

验证：`selftest` 38/38、`robustness` 70/70、`stability` 99/99、
`audit --strict` 0 error / 0 warn、`validate-metadata` PASSED。

---

## v3.4.2（2026-09-17）· 开源就绪：补齐社区基础设施 + 修 6 处文档失真

为公开发布做的一轮整理。**没有改动任何脚本行为**，所以是 PATCH。

### 新增：开源社区基础设施

| 文件 | 作用 |
|---|---|
| `.github/workflows/ci.yml` | 自测 CI：py3.8/3.11/3.13 × ubuntu/macos/windows，跑三套测试 + `audit.py --strict` |
| `.github/workflows/release.yml` | 打 tag 发版；**先校验 tag 与 `VERSION` 一致**，不一致直接失败 |
| `.github/validate-metadata.py` | 元数据校验：JSON/YAML 解析、CITATION.cff 必填字段与版本、文档引用路径是否存在、占位符与隐私残留 |
| `.github/ISSUE_TEMPLATE/` | bug / feature 表单 + `config.yml`（禁用空白 issue，安全问题导流到 Security Advisory） |
| `.github/PULL_REQUEST_TEMPLATE.md` | 强制填写「验证过什么」与硬约束自查 |
| `CODE_OF_CONDUCT.md` | Contributor Covenant 2.1，并加了一条本项目特有的：**编造事实与骚扰同等级处理** |
| `RELEASE.md` | 发版流程：六处版本号、检查清单、引用纪律、出错怎么办 |
| `MAINTAINERS.md` | 维护者与联系渠道分工 |
| `.editorconfig` | 统一 UTF-8 / LF / 缩进 |

> `validate-metadata.py` 是唯一允许用第三方库（PyYAML）的脚本，
> 它放在 `.github/` 而不是 `scripts/`，就是为了不污染产品侧的"零依赖"审计。

### 修掉 6 处文档失真

| # | 位置 | 问题 | 修法 |
|---|---|---|---|
| 1 | `README.md` 目录树 | 写「12 篇深度参考」，实际 17 篇 | 改为 17，并补 `17-vendor-and-induction.md` |
| 2 | `README.md` 目录树 | `assets/` 块**重复出现两次**，且缺 `audit.py`、全部新增文件 | 重写目录树，脚本标注 14 个 |
| 3 | `README.md` 目录树 | `CHANGELOG.md` 描述停留在「v1 → v2 变更」 | 改为不带版本号的「版本变更（Keep a Changelog 格式）」，避免以后再漂移 |
| 4 | `README.en.md` 测试表 | 只有两套、写 29 条（实际 38） | 改三套 38 / 70 / 99，并补 `stability_test.py` 的定位说明 |
| 5 | `README.en.md` 现状行 | 「29/29 and 70/70 passing」与实际不符 | 改为 38/38、70/70、99/99 + `audit.py` clean |
| 6 | `README.en.md` 目录树 | 写「15 deep references」，实际 17 | 改为 17 |

### 补上的内容

- 两个 README 都加了：`git clone` 安装方式、装完验证命令、徽章（MIT / Python / CI / Release / 零依赖）、「参与项目」章节
- `CONTRIBUTING.md` 加了「许可与署名」：**inbound = outbound**，贡献以 MIT 授权给下游
- 两个 README 都补了 Windows 用户提示：hook 配置后**务必手动触发一次**，因为 hook 解析失败是静默放行的

验证：`selftest.py` 38/38、`robustness_test.py` 70/70、`stability_test.py` 99/99、
`audit.py --strict` 0 error / 0 warn、`validate-metadata.py` PASSED。

---

## v3.4.1（2026-09-17）· 稳定性测试：新增第三套测试 + 修 7 个问题

动机：做了一轮完整的稳定性回归，发现**前两套测试（selftest 38 / robustness 70）覆盖不到的失效面**——
它们都在测"脚本行为对不对"，但技能包还会以别的方式坏掉。

### 新增 `scripts/stability_test.py`（99 条工程一致性）

七组：A 编译与入口 / B 幂等与并发 / C 异常输入 fuzz / D 环境 / E 文档与版本一致性 /
F 资产合法性 / G 安装目录同步（可 `--no-install-check` 跳过，或用 `DEHALLU_INSTALLED` 指定路径）。

它抓到的问题，前两套一条都抓不到：
- hook 被改出 `IndentationError`（`selftest` 里 hook 用例只跑 2 个，另外 2 个坏了不会报）
- 文档写的版本号与 `VERSION` 文件不一致
- 文档里写的引用路径（形如 `references/` 下某个文件）其实不存在
- 工作区改完了**忘了同步到安装目录**（G 组逐字节比对）

### 修掉 7 个问题

| # | 问题 | 修法 |
|---|---|---|
| 1 | 6 个脚本读 JSON 时假设顶层是对象，喂 `[]` / `null` 直接抛 `AttributeError` 并打 Traceback | `_common.py` 新增 `load_json_object()`：非对象时按用法错误退出（3），不打栈 |
| 2 | 4 个 Claude Code hook 收到非对象 JSON（如 `[1,2]`）时抛异常 | 包一层 `try` + `isinstance(event, dict)` 兜底；**hook 一律 fail-open**——拿不到字段就放行，绝不能卡死正常流程 |
| 3 | `regression.py` 误用严格对象读法，**顶层数组其实是合法输入**（`robustness` 第 70 条回归）→ 退出码 0 变 3 | 改回 `load_json_file` + 分支，并加注释说明"这里不能严格" |
| 4 | `selftest.py` / `robustness_test.py` 完全没接参数解析，传 `--help` 被静默忽略、直接跑全套 | 补 `-h/--help` 分支，打印真实用法与可选组名 |
| 5 | `i18n/en/SKILL.md`、`README.en.md` 仍写 "29 smoke cases"（实际 38） | 改为 38 |
| 6 | 本轮我自己的批量补丁把 2 个 hook 改出语法错误、误删 66 行真实代码 | 从安装目录副本恢复后逐个用 `Edit` 重打，并与安装版逐行 diff 确认只有 +7 行补丁 |
| 7 | `stability_test.py` 跑 hook 时没指定 cwd，`precompact_snapshot` 把快照写进了用户当前目录（实测污染出 20 个文件） | hook 调用统一 `cwd=tmp`；已清理残留 |

> 第 6 条值得单独记：**没有 git 的工作区里做批量文本替换是危险的**。
> 这次靠安装目录里的旧副本才恢复回来。后续同类改动优先用精确 `Edit`，不要用脚本批量改。

### 文档同步

`README.md`（两套测试→三套 + 目录树）、`CONTRIBUTING.md`（新增测试怎么写一节）、
`SKILL.md` / `i18n/en/SKILL.md`（命令块）、`README.en.md`（目录树 + 命令块）、
`references/15-stability-performance.md` §6、`assets/ci/github-actions.yml`（加 stability 步骤）。

验证：`selftest.py` 38/38、`robustness_test.py` 70/70、`stability_test.py` 99/99、`audit.py` 0 error / 0 warn。

---

## v3.4.0（2026-09-16）· 诱导型幻觉 + 厂商一手做法 + 分档实证

> 附带修正：`VERSION` 文件此前停在 3.2.0（v3.3.0 未同步），本次一并校正为 3.4.0。

动机：前几版把幻觉等价于"不知道却硬答"。但存在**另一类**——模型知道正确答案，
却因为用户先表态而改口。这在之前整套框架里是盲区。

### 新增 `references/17-vendor-and-induction.md`

- **OpenAI 一手**（`openai.com/index/why-language-models-hallucinate/`，2025-09-05，arXiv 2509.04664）：
  幻觉 = 预训练侧任意低频事实无模式可学 + 评测侧"只看 accuracy 奖励猜测"。
  SimpleQA 对照（弃权 52%/错误 26% vs 弃权 1%/错误 75%）证明"更高准确率"与"更少幻觉"可以是相反方向。
  另记官方澄清的四个误解（幻觉不可避免？需要更大的模型？做一个好 eval 就够？）
- **Anthropic 一手**（官方文档 *Reduce hallucinations*，URL 已迁 `platform.claude.com`）：
  三条基础策略 + 四条高级技巧原文要点；官方自述"显著减少但不能完全消除"。
  并记录**两处有意偏离**：Best-of-N 降级为及格线信号、Iterative refinement 改为隔离子任务（理由：CoVe factored）
- **谄媚（一手）**：*Science* 391(6792) DOI 10.1126/science.aec8352（11 模型比人类多肯定用户 49%；
  N=2,405 预注册实验）；arXiv 2602.19141（即使理想贝叶斯用户也中招，且两种缓解均失效，
  "事实型谄媚者"比编造型更危险）
- **中性重述模板**：把用户原话交给验证者之前必做的三步

### 新增铁律 9：用户的立场不许进入证据链

- 核查前必须中性重述（剥掉"我觉得/肯定是/难道不是"）
- **同源即非独立**：多次采样 / 多个 agent 说同一句话，先查是否共享来源，共享则算 1 条
- 工作流新增 **[4.5] 中性重述** 步

### 修正：自一致性的天花板（改 `12` + `SKILL.md`）

一手 arXiv 2607.11414：8/8 采样全部一致的答案里仍有 **15–23%** 是错的；
该子集上 logprob 与 P(True) 判别力掉到 0.55–0.63 AUROC。
→ `selfcheck.py` 高一致从"确认依据"降为**及格线**；升 `confirmed` 仍需 ≥2 独立一手源。

### 分档打法拿到一手实证（改 `16`）

- arXiv 2601.00513：7–9B 模型 **50–69% 的正确答案推理链本身有错**；
  self-critique **有害**（d=−0.14~−0.33）、RAG **有益**（d=0.23~0.93）；蒸馏验证器 F1 0.86 / 快 100×
- ICCSA 2026（DOI 10.1007/978-3-032-30488-9_39）：3B–4B 上 8 种方法实测，**无单一方法全任务占优**
- 新增全档位共同三条禁忌（前提不得进证据链 / 一致性不当确认 / 小模型禁止 self-critique）

### 检测手段按"模型权限"分层（17 章 §5）

黑盒（确定性硬核查 > NLI > 采样一致性）/ 有 logits / 有 hidden states / 有梯度。
新增 Diversion Decoding（arXiv 2607.10476）：AUROC 74.66%(7B)/78.49%(13B)，
expansion ratio 3.6 vs 语义熵 10 —— 比纯采样更划算。

### 代码改动 `scripts/model_profile.py`

- `VENDOR_MECHANISMS` 全部换成**一手来源标注**（此前是无出处的简述）
- 新增 `UNIVERSAL_CONTROLS`：**与档位无关**的共同控制项，所有 profile 输出都会带上
- B 档 notes 补 self-critique 有害的实证
- 修一处重复提示（推理型提示被打印两次）
- `selftest.py` 38 条全通过

### 引用纪律（延续）

本次检索出现大量 SEO 型内容，已明确**不采信**并写入 `13-frontier-2026.md` §5.1：
型号幻觉率对比表、任意型号的 benchmark 得分表、以及对 HalluScan（arXiv 2605.02443）
与 arXiv 摘要**互斥**的一套转述。

---

## v3.3.0（2026-09-16）· 模型适配层

动机：前几版隐含假设"模型有足够元认知"。但**同一套核查策略不能套在所有模型上**——
CoVe 与自一致性的前提是"模型知道自己不知道"，弱模型没有这个前提。

### 新增 `scripts/model_profile.py`（模型能力分档 → 核查策略）

分档的核心变量是 **trust_selfcheck（自我核查是否可信）**：

| 档 | 自我核查 | 单次声明上限 | 打法 |
|---|---|---|---|
| S（前沿旗舰） | ✅ | 40 | CoVe 隔离验证 + 原生引用 + 外部硬核查兜底 |
| A（主力） | ✅ 基本 | 25 | CoVe 可用；低置信才上多模型交叉 |
| B（轻量/中端） | ❌ | 12 | **不依赖自我核查**：全走外部脚本 + 强制引用 |
| C（小模型/边缘） | ❌ | 5 | 只做可判定项核查，禁止开放式事实结论 |

- 未知型号一律按 **B 档**（保守默认，绝不放松）
- 联网能力属于**运行环境**而非模型，用 `--net on|off` 单独声明
- 无联网 + 弱模型 → 风险等级自动上调 L2（需人工闸门）
- 推理型模型自动标注"推理链不作为证据，只用于生成验证问题"
- 输出的是**可执行策略**（`use_model_selfcheck` / `require_external_evidence` / `max_claims_per_pass`），不是描述

### 新增 `references/16-model-adaptation.md`

- 四档定义 + 各档核查手段对照表（CoVe / 自一致性 / 外部硬核查 / 人工闸门该不该用）
- **厂商官方机制对照**：Anthropic 原生 Citations API（声明锚定到源文档 char/page 区间）
  + Extended Thinking；OpenAI 联网检索与官方"引用也可能编造"的口径；
  Google Grounding；DeepSeek 推理型；开源小模型
- **NIST 的 confabulation 定义**（一手）：自信呈现的错误内容，且生成的引用本身可能是编造的
- 环境适配：无联网 / 短上下文 / 推理型 / 无 logprobs / 多模态 各自的调整
- 弱模型六条特别规则（禁止原地复查、压声明数、无源即删更严、风险上调、不做核查主体、强制输出结构）

### 引用纪律（重要）

本轮搜索出现的**型号级幻觉率与准确率数字**（如"某型号幻觉率 15–25%""某型号事实错误 −68%"
"TruthfulQA/HaluEval/SimpleQA 型号得分表"）在不同来源间**互相矛盾**，
已在 `ATTRIBUTIONS.md` 中明确列为 **"未采信，引用前必须回溯官方 system card"**。
本套件不引用、不采信这类数字。

### 其他

- SKILL.md：启动三问 → **四问**（新增 Q0 模型档位）
- selftest 新增 5 条 model_profile 用例 → **38/38 通过**
- README 补"模型适配"章节

---

### 一、开源合规（新增 `scripts/audit.py`，自动化审计）

审计脚本检查六类问题，发布前跑，现在 **0 ERROR / 0 WARN**：

| 类别 | 检查内容 |
|---|---|
| 元数据 | LICENSE / NOTICE / CONTRIBUTING / SECURITY / CITATION.cff / VERSION / README(.en) / i18n 是否齐备 |
| 许可证 | 每个 .py 是否有 `SPDX-License-Identifier: MIT` |
| 依赖洁净 | AST 解析 import，非标准库模块即报错（守住"零第三方依赖"承诺） |
| 隐私/可移植 | 残留家目录路径（**本机绝对路径**）、疑似密钥、邮箱 |
| 版本一致 | VERSION = SKILL.md frontmatter = CHANGELOG 顶部 |
| 文档完整 | README 是否覆盖关键脚本与协议 |

### 二、靠审计发现的真问题（已修）

- **11 个文档文件残留本机用户目录的绝对路径**（形如 Windows 用户目录，开源发布即隐私泄露）—— 已全部替换为
  `python3` / `~/.workbuddy/skills/...` / `<skill 目录>`。
- 14 个 .py 缺 SPDX 头 —— 已补齐。

### 三、新增开源文件

`NOTICE`（声明不含第三方代码 + 无商标隶属）、`CONTRIBUTING.md`（三条硬规则：禁止第三方依赖、
事实必溯源、改脚本必加测试）、`SECURITY.md`（工具性质说明 + 私有报告通道 + 提高严重度的缺陷类别）、
`CITATION.cff`（含 14 条被引论文的规范化引用）、`VERSION`、`.gitignore`。

### 四、国际化（面向全球）

- `i18n/en/SKILL.md` —— 英文主入口（八条铁律 / 八步工作流 / 闸门 / 退出码 / 15 篇参考索引）
- `README.en.md` —— 完整英文说明

### 五、效率与开放性

- `dep_guard.py --changed-only [--git-ref HEAD]` —— **增量核查**，只扫 git 变更文件；
  git 不可用时明确报用法错误（不静默退化为全量扫描，避免"以为扫了其实没扫"）
- 新增 `scripts/verifiers.py` —— 可插拔检测器桥接（OpenFactCheck 三插槽落地）。
  只探测不 import（无副作用、不拖慢），回答"本机有哪些外部检测器可用"（deepeval / ragas /
  cleanlab / trulens / sentence-transformers / transformers 等），支持 `--require` 做 CI 门禁。
  **缺失不是错误** —— 内置确定性脚本永远可用。

### 测试现状

`selftest.py` **33/33** · `robustness_test.py` **70/70** · `audit.py` **0 ERROR / 0 WARN**

---

动机：上一版只验证了正常路径。这一版补**深度健壮性测试**，并修掉它发现的两个真缺陷。

### 新增 `scripts/robustness_test.py`（70 条深度测试）

与 `selftest.py`（29 条快速冒烟）分工：冒烟每次改完跑，深度测试发版/换环境跑。

核心断言不是"结果对不对"，而是：
1. **绝不出现 Traceback**（捕获 stderr 异常栈）
2. **退出码必须落在 {0,1,2,3}**
3. `--json` 输出必须可解析
4. 幂等：同样输入跑两次结果一致
5. 性能预算：200 文件 < 5s；1000 条声明 lint < 10s

覆盖的刁钻输入：GBK 文件、UTF-8 BOM、空文件、>2MB 大文件、二进制、中文+空格路径、
50 层嵌套目录、node_modules、损坏 JSON、字段类型全错的契约、5 进程并发写同一缓存目录、
写坏的缓存文件、`--timeout 0`、`--max-checks -1`、`--jobs -5`、超长命令、emoji、
hook 的垃圾/超长/缺字段输入（20 条 hook 用例）。

### 修复（由该测试发现，均为真缺陷）

1. **argparse 参数错误返回 2，与"存在未验证"撞码** —— 下游会把"命令写错"误读成
   "有未验证项"。新增 `_common.ArgParser`，全部脚本参数错误统一走 **3**。
2. **selfcheck 的"低一致"占用了 3** —— 与"用法错误"冲突。低一致改为 **4**，3 专用于错误。
   （同步更新 references/12、README 退出码表、selftest 用例）

### 测试现状

`selftest.py` **29/29 通过**，`robustness_test.py` **70/70 通过**。

---

目标：把"覆盖全"推进到"能打、不崩、有据可查"。三条主线：**创新融合 / 稳定性与效率 / 开放优化**。

### 一、创新融合：补上编码场景最危险的一环

- **新增 `scripts/dep_guard.py`**：依赖与符号幻觉防护。
  - 提取 import（Python / JS·TS / Rust / Go / Kotlin·Java）
  - 幻影路径（内部相对导入指向不存在的文件）→ BLOCK
  - 幻影依赖（该生态 manifest 未声明）→ BLOCK
  - 包不存在（npm / PyPI registry）→ BLOCK
  - **slopsquat 特征**：首版发布 < 90 天 → SUSPICIOUS
  - typosquat 特征（与知名包编辑距离过近）→ SUSPICIOUS
  - 命名导入的导出符号校验（默认导入不查，避免误报）
  - 防误报设计：跨生态不判、标准库不判、gradle 不做未声明判定
- **新增 `references/14-supply-chain-code.md`**：包幻觉 → 供应链攻击（slopsquatting）的六层防线
- **新增 `references/13-frontier-2026.md`**：补 6 篇 2026 论文（HalluScan 2605.02443、LLM Ghostbusters 2605.01047、LaaB 2605.03971、BALTO 2606.15893、HalluGuard 2601.18753、视觉源幻觉 2609.00231）+ 开源生态现状 + 本套件的层间定位

### 二、稳定性与效率

- **缓存**：网络核查结果缓存 6 小时（DEHALLU_CACHE_DIR 可配）
- **并发**：网络项默认 4 并发（--jobs，上限 16），线程池不可用时自动退化为串行
- **重试**：瞬时故障重试 1 次（--retries），指数退避
- **预算**：--max-checks 防止核查失控，超预算项记为未验证并告警
- **原子写**：所有 JSON 落盘先写 .tmp 再 replace，不会留下半截文件
- **Claude Code 8 次阻断上限修复**（关键）：Stop hook 连续阻断 8 次会被宿主强制放行。
  `verify_gate.py` 现在：首次 exit 2 → 检测到 `stop_hook_active` 或接近上限时改用
  `hookSpecificOutput.additionalContext`（继续回合但不计阻断）→ 超硬上限（6 次）记录并放行。
  **闸门不会失效，也不会把用户卡死。**
- **新增 `references/15-stability-performance.md`**：环境矩阵（无网/沙箱/只读/GBK/代理/CI）+ 六条不崩溃纪律 + 模型侧防"当掉"

### 三、开放优化

- **新增 `scripts/pipeline.py`**：一键编排 hardcheck → dep_guard → claim_lint，出一份报告一个退出码
- **新增 `hooks/subagent_gate.py`**（SubagentStop）：子 agent 报告含"已完成/已验证"却无证据 → 拦截补证据
- **新增 `hooks/precompact_snapshot.py`**（PreCompact）：压缩前把账本/执行声明/git 状态落盘，压缩后可读回，专治"记忆漂移"
- **CI 集成示例** `assets/ci/github-actions.yml`
- **自检从 17 条扩到 28 条**（新增 dep_guard 干净/脏项目、pipeline、并发、subagent_gate、precompact、阻断循环保护）

### 变更

- SKILL.md：铁律 7 → **8 条**（新增"依赖与包名必须能解析"）；红线加"包名与 import 路径"
- ATTRIBUTIONS.md：补 6 篇论文 + Promptfoo / hallucination-guard 等同源项目 + slopsquatting 报道的二手标注
- settings-hooks.json：新增 SubagentStop / PreCompact；补官方退出码与上限语义说明

---

**定位变化**：从"提示词约束"升级为"提示词 + 可执行闸门"。v1 里所有"必须检查"的项，v2 里凡是能被脚本判定的，都变成了脚本。

### 新增：可执行闸门（scripts/）

| 脚本 | 作用 | 退出码 |
|---|---|---|
| `hardcheck.py` | URL / DOI / 文件 / 命令 / PyPI / npm 存在性核查，fail-closed | 0/1/2/3 |
| `claim_lint.py` | 输出契约闸门：校验 `confirmed` 是否真有 ≥2 独立源、是否找过反证、`observed` 是否有观测时间、低置信是否附反例、L2 是否走人工闸门、执行声明是否有证据 | 0/1/3 |
| `ledger.py` | 项目账本：add / get / list / check / remove；`check --drift` 实际读文件比对账本与现实 | 0/1/3 |
| `selfcheck.py` | 采样一致性统计（无原文不可检索时的兜底） | 0/2/3 |
| `regression.py` | 幻觉案例回归集 | 0/1/3 |

全部纯 Python 标准库，3.8+，Windows/Unix 双兼容，支持 `--offline`。

### 新增：大项目模式（references/07-large-project.md）

针对"超级庞大项目 + 多会话 + 多子 agent"的五类累积性幻觉：

- 记忆漂移 / 状态幻觉 / 约定漂移 / 回声幻觉 / 跨会话遗忘
- 六条大项目铁律（先读后说、账本即真相、账本非免检、子 agent 报告不采信、完成标准先定义、里程碑闸门）
- 决策账本 + 漂移检测（`ledger.py check --drift`）
- 引用先行（长文档 >20k tokens 先逐字抽引文）

### 新增：Harness 适配层（adapters/）

- **Claude Code**：`settings-hooks.json` + `verify_gate.py`（Stop 闸门）+ `guard_bash.py`（PreToolUse 拦截不可逆命令）
- **DeepSeek**：推理链非证据、无 logprobs 时的置信度替代、中文场景一手源规则、system prompt
- **通用**：Codex / Cursor / Cline / Roo / Gemini CLI / 自研 的规则文件位置与收尾脚本

### 新增：references 从 5 篇扩到 12 篇

01 核心原理 · 02 上下文判定 · 03 硬核查 · 04 核查工作流 · 05 标签与置信度 · 06 成本路由 ·
**07 大项目** · **08 编码模式** · 09 反模式与自检 · 10 度量与回归 · **11 Harness 适配** · **12 不确定性校准**

### 新增：协议与出处

- `LICENSE`（MIT）
- `ATTRIBUTIONS.md`：借鉴项目与论文的 License、出处、**一手/二手分档**，并列出本套件内部所有需回溯的二手数字

### 变更

- SKILL.md：铁律 5 条 → **7 条**（新增"大项目里记忆不是证据""工具失败 ≠ 通过"）
- 工作流：5 步 + 执行同闸 → **8 步 + 一道闸门**（拆出原子化、硬核查、打分，末尾接 `claim_lint`）
- 输出契约 schema：新增 `retrieval_performed`、`metrics`、`hard_checks.summary/removed`
- 新增 `examples/`（含一个**故意做错**的 `claims-bad.json`，用于验证闸门真的会拦）
- 新增 `assets/templates/`（claims / checks / 子 agent 核查模板）

### 未变化（刻意保留）

- 五标签体系、先证伪、90 天过期、CoVe 隔离验证、ADR 成本路由 —— 这些是 v1 就已经验证过的核心，不动。

---

## v1.0.0（2026-09-16）

初版：SKILL.md + 5 篇 references + claim-schema.json。纯提示词方案。
