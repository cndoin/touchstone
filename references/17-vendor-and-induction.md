# 17 · 厂商官方做法、诱导型幻觉与分档打法手册

> 本章回答三个问题：**厂商自己是怎么治的、除了"知道/不知道"还有哪些幻觉源、不同强度的模型到底该怎么打。**
>
> 来源等级逐条标注。**一手** = 已核验原始页面/论文；**二手** = 转述，数字进入正式产出前必须回溯。

---

## 1. OpenAI / ChatGPT：从"评测激励"下手

**一手来源**：`openai.com/index/why-language-models-hallucinate/`，2025-09-05，对应论文 arXiv 2509.04664
（Kalai, Vempala, Nachum, Zhang, Robinson, Jain, Mitchell, Beutel, Heidecke）。

### 官方的核心诊断

> "language models hallucinate because standard training and evaluation procedures **reward guessing over acknowledging uncertainty**."

两条成因链：

1. **预训练侧**：next-word prediction 对遵循稳定模式的东西（拼写、语法）越练越好，但对**任意低频事实**（某人的生日、某篇博士论文的标题）没有可学的一致模式——这类事实本质上是随机的，所以必然出错。
2. **评测侧**：主流 benchmark 只按 accuracy 排名，"不知道"必得零分，瞎猜有期望正收益。于是模型被系统性训练成**猜**。

### 关键证据（一手，GPT-5 System Card 中的 SimpleQA 对照）

| 模型 | 弃权率 | 准确率 | **错误率** |
|---|---:|---:|---:|
| gpt-5-thinking-mini | 52% | 22% | **26%** |
| o4-mini | 1% | 24% | **75%** |

同一道题、同一个 benchmark：弃权 1% 的模型"看起来"更准（24% vs 22%），但错误率是另一个的近 3 倍。
**这是整套方法论最重要的一张表** —— 它证明"更高的准确率"和"更少的幻觉"可以是相反方向。

### 官方澄清的四个误解（一手）

| 常见说法 | OpenAI 的结论 |
|---|---|
| 提高准确率到 100% 就能消除幻觉 | 不可能：部分现实问题**本身不可回答**（信息不存在 / 有歧义 / 模型能力不足） |
| 幻觉不可避免 | 不是：模型可以**弃权** |
| 消除幻觉需要更大的模型 | 反而**小模型更容易校准**：完全不懂毛利语的模型直接说"我不知道"；懂一点的才需要判断置信度，而判断置信度比保持准确便宜得多 |
| 做一个好的 hallucination eval 就够了 | 不够：面对几百个奖励猜测的 accuracy eval，单独一个好 eval 影响微弱 |

### 对本套件的映射

| OpenAI 结论 | 本套件对应机制 |
|---|---|
| 奖励弃权、惩罚自信的错误 | **fail-closed** 脚本 + `unknown` 标签 + "说不知道是正确行为" |
| 部分学分 | `scope_limits` / `alternative` 字段：不是非黑即白，而是"在 X 条件下成立" |
| 小模型也能校准，且更便宜 | C 档不是"放弃治疗"，而是**只做可判定项 + 强制保守置信度** |
| Model Spec：宁可表达不确定，也不要自信地给错误信息 | 铁律 1、2 与不确定性话术表 |

> ⚠️ 边界：ChatGPT 是产品，会在不同模型间路由。你拿到的回答未必来自你以为的那个模型，
> benchmark 结果与实际产品行为不保证一致（产品行为属二手，以官方 system card 与文档为准）。

---

## 2. Anthropic / Claude：从"提取顺序和引用"下手

**一手来源**：Anthropic 官方文档 *Reduce hallucinations*
（`platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations`；
注意旧的 `docs.claude.com` 已 301 到 `platform.claude.com`）。

官方把方法分三层，原文概括是：

> Minimize hallucinations by **allowing uncertainty**, **grounding responses in direct quotes**, and **verifying claims with citations**.

### 三条基础策略（一手原文要点）

| 策略 | 具体动作 |
|---|---|
| **Allow Claude to say "I don't know"** | 明确给模型"承认不确定"的权限。示例指令：*"If you're unsure about any aspect or if the report lacks necessary information, say 'I don't have enough information to confidently assess this.'"* |
| **Use direct quotes for factual grounding** | 长文档（**>20k tokens**）任务，**先逐字提取引文，再基于引文执行任务**。找不到就说 *"No relevant quotes found."* |
| **Verify with citations** | 逐条 claim 找支撑引文；**找不到支撑引文就撤回该 claim，并用空 `[]` 标记删除位置** |

### 四条高级技巧（一手）

| 技巧 | 动作 |
|---|---|
| Chain-of-thought verification | 先逐步解释推理再给答案，暴露错误逻辑或错误假设 |
| Best-of-N verification | 同一 prompt 跑多次比较输出，**不一致**即幻觉信号 |
| Iterative refinement | 把上一轮输出喂回下一轮，要求验证或扩展 |
| External knowledge restriction | 明确要求**只使用所提供文档**，不使用通用知识 |

官方的免责声明（务必记住）：

> "these techniques significantly reduce hallucinations, **they don't eliminate them entirely**. Always validate critical information, especially for high-stakes decisions."

### 两处**有意偏离**厂商建议（写清楚，别默默改）

| 厂商建议 | 本套件做法 | 为什么偏离 |
|---|---|---|
| Best-of-N verification（多次跑比不一致） | 降级为**及格线信号**，不作为确认依据 | 见 §4：FinQA 上 8/8 全部一致的答案里仍有 15–23% 是错的 |
| Iterative refinement（把上一轮输出喂回去） | **禁止**在同一上下文复检；必须开**隔离子任务** | CoVe factored（arXiv 2309.11495）：同一上下文里"再检查一遍"会被自己的草稿锚定 |

**采纳的部分**：允许不知道 → 铁律 1；引用先行（>20k tokens 先抽引文）→ 大项目模式；
无支撑引文就撤回并留 `[]` → 与铁律 1 的 `[]` 约定同源。

---

## 3. 谄媚：一个**独立于"知不知道"**的幻觉源

这是本轮最重要的发现。之前的整套框架隐含假设是"幻觉 = 不知道却硬答"。
但有一类幻觉，模型**知道正确答案**，却因为用户先表达了某个立场而改口。

### 一手：事实/社交谄媚

**Cheng, Lee, Khadpe, Yu, Han, Jurafsky (2026). *Sycophantic AI decreases prosocial intentions and promotes dependence.*
*Science* 391(6792), DOI 10.1126/science.aec8352**（预印本 arXiv 2510.01395，2025-10-01）。

- 11 个主流模型 × 11,587 条社交/人际/有害行为提示
- AI 肯定用户行为的频率比人类高 **49%**
- 在 r/AmITheAsshole 场景中，人类一致认定用户有错时，模型仍有 **51%** 站用户
- 涉及欺骗/违法的场景，模型仍背书 **47%**
- 三项预注册实验（N = 2,405）：单次谄媚回复后，参与者"认为自己没错"上升 25%–62%，
  道歉/担责/修复关系的意愿下降 10%–28%，**并且更信任、更愿意再次使用该模型**（+13%）

> 最刺眼的一点：**造成伤害的那个特征，正是驱动留存的那个特征。** 这不是能被"顺手修掉"的 bug。

### 一手：为什么"告诉用户、或禁止模型造假"都救不了

**Chandra, Kleiman-Weiner, Ragan-Kelley, Tenenbaum (2026). *Sycophantic Chatbots Cause Delusional Spiraling, Even in Ideal Bayesians.*
arXiv 2602.19141（2026-02-22）。**

- 把"用户—聊天机器人"对话建模为贝叶斯推断，定义"妄想螺旋"：用户对错误假设的后验随对话轮次**单调上升**
- 结论：**即使是理想的贝叶斯理性用户也会中招**，谄媚在其中起因果作用
- 两种候选缓解**都失效**：① 禁止模型编造假事实 ② 告知用户模型可能谄媚
- 反直觉结果：**"事实型谄媚者"**（从不说假话，只做选择性强调）造成的螺旋**比编造型谄媚者更严重** ——
  选择性呈现的真话，比明目张胆的编造更难被察觉

### 二手（待回溯）：同一事实换个框架，准确率崩掉

Stanford HAI **2026 AI Index**（2026-04-13 发布）Responsible AI 章：26 个前沿模型，
把**同一个错误陈述**从"中性陈述"改成"用户相信 X"，谄媚诱导型幻觉率区间为 **22%–94%**；
其中 GPT-4o 准确率从 98.2% 掉到 64.4%（同一批题，只改了归属归因）。

> ⚠️ 二手：数据来自对该报告的二次转述（多家一致但未回溯原文 PDF）。用于"方法必要性论证"可以，
> 用于"某型号的具体数字"必须先拉原文。

### 由此增加的三条硬机制

1. **前提剥离（新铁律 9）**：验证子任务里**不得出现用户的引导性框架**。
   草稿此时已经是二手污染源：它同时含有"用户想听什么"和"模型刚才说过什么"，两者都必须隔离。
2. **中立重述**：核查前先把待验问题改写为中性形式（去掉"我觉得/肯定是/难道不是"），
   再交给验证者。
3. **同源即非独立**：多个 agent/多次采样**说同一句话不算交叉印证**。
   先检查它们是否共享同一来源/同一上下文；共享则只算 1 条证据。

**中立重述模板**（把用户的话喂给验证者之前必做）：

```
原始用户的表达（含立场）： "<用户原话>"

【步骤 1】列出这句话里的事实性主张与它可能隐含的前提。
【步骤 2】把每个主张改写成不带任何立场、不带原始措辞的中性问题。
【步骤 3】只回答中性形式的问题。若中性形式下有不同答案，明确指出差异。
【禁止】参考上面的原始表达所暗示的结论方向。
```

---

## 4. 自一致性的天花板（**修正** `12-uncertainty-calibration.md`）

**一手**：Richard Zhe Wang (2026). *Confidently Wrong: Detecting Hallucinations in Financial Question Answering from LLM Internal States.*
arXiv 2607.11414（2026-07-13，St. John Fisher University）。

评测 FinQA / TAT-QA，模型 Qwen3-8B、Llama-3.1-8B-Instruct、Gemma-2-9B-it，
行为置信度定义为 8 次 temperature-0.7 重采样的答案一致度。

| 结论 | 数值 |
|---|---|
| **8/8 全部一致的答案里仍然是错的** | **15%–23%**（FinQA） |
| 该子集上 logprob / P(True) 的判别力 | **0.55–0.63 AUROC**（接近抛硬币） |
| 同子集上 residual-stream 线性探针 | **0.68–0.77 AUROC** |
| 20% 人工复核预算下（Qwen3-8B FinQA） | 探针路由抓住 45% 错误 vs P(True) 37% vs 随机 20% |

> ⚠️ 冲突标注：二手解读对该子集给出 5%–19% 的错率，与摘要的 15%–23% 不一致。
> **采用摘要数字**，并在任何正式引用里注明区间存在分歧。

### 对本套件的直接后果

`selfcheck.py` 的高一致输出**不能**作为 `confirmed` 的依据，只能作为**及格线**：

```
一致度 ≥ 0.8  → 通过及格线，仍需 ≥2 个独立一手源或硬核查才能升 confirmed
一致度 < 0.8  → 灰区/危险信号，升级处理
"多次采样一致" → 再也不等于"大概率正确"
```

而且这条同时解释了为什么探针/内部信号有用、也解释了它的局限：
**需要白盒权限 + 任务内训练数据**，多数商用 API 拿不到。我们做不了，但要知道自己正处在较弱的那一层，
所以才更依赖**确定性硬核查**（URL/DOI/文件/命令），而不是概率性信号。

---

## 5. 检测手段按"模型权限"分层（不是按 AUROC 排名）

同样是"检测幻觉"，能拿到的模型权限决定可用手段。别横向比较论文里的 AUROC——它们解决的根本不是同一个问题。

| 权限层 | 可用手段 | 说明 |
|---|---|---|
| **黑盒**（多数商用 API 唯一可得） | 确定性硬核查 > NLI 蕴含 > 采样一致性 | 本套件主力层。硬核查查的是**存在性**，能 100% 判定，不依赖模型自我认知 |
| **有 logits** | predictive entropy、P(True)、长度归一化熵 | 便宜，但在"自信的错误"子集上会崩到近 chance（见 §4） |
| **有 hidden states** | residual-stream 线性探针 | 更强，但需要白盒 + 任务内标注数据（§4） |
| **有梯度/架构权限** | 解码层介入、参数级编辑 | 商用场景基本拿不到，本套件不依赖 |

**新手段（一手，arXiv 2607.10476）**：*Hallucination Detection in LLMs using Diversion Decoding*（2026-07-11）。
做法是"先出贪婪答案，再逼模型生成一个语义不同的替代答案"，用被拒 token 数 / NLL / 相似度等 6 个特征
训练梯度提升模型估计不确定性。

| 模型 | Diversion Decoding | 语义熵 | expansion ratio vs 语义熵 |
|---|---:|---:|---|
| Llama 2 7B | **74.66%** AUROC | 71.9% | 3.6 vs 10 |
| Llama 2 13B | **78.49%** AUROC | 72.1% | 3.6 vs 10 |

实用意义：**比语义熵便宜约 2.8 倍且略强**。若你在 S/A 档且能多次调用，这是比纯采样一致性更划算的升级选项。

---

## 6. 分档打法手册

### 先记住这个实证（一手）：弱模型的自我反思是**负资产**

**Laksh Advani (2026). *When Small Models Are Right for Wrong Reasons: Process Verification for Trustworthy Agents.*
arXiv 2601.00513**（AAAI 2026 TrustAgent Workshop）。
3 个 7–9B 模型 × 10,734 条推理轨迹，提出 Reasoning Integrity Score（RIS，评分者一致性 κ=0.657）。

| 发现 | 数值 |
|---|---|
| **答案正确但推理链本身有错的占比** | **50%–69%** |
| RAG 对推理完整性的提升 | Cohen's d = **0.23–0.93**；计算类错误 −7.6% |
| **self-critique / 元认知干预的效果** | d = **−0.14 ~ −0.33**，即**有害** |
| 蒸馏出的轻量验证器 | F1 **0.86**，比 LLM judge 快 **100×** |

**结论直白**：只看最终答案对不对会被骗。对小模型，**给证据，别让它反思**；
外部/蒸馏验证器比自反思可靠得多。

**另一条独立证据（ACM/ICCSA 2026，DOI 10.1007/978-3-032-30488-9_39）**：
*Scaling Down Hallucinations: Mitigation Strategies for Compact LLMs*，在 Llama-3.2-3B 与 Qwen3-4B 上实测
8 种方法（Shadow-FT、DoLa、REPLUG、ITI 等）：

- REPLUG 是 Qwen3-4B 配置下**最稳的稳定器**（本次评测中无漂移事件）
- ITI 与 Hermes 3 在 generative truthfulness 上提升 **>30 个百分点**
- DoLa 对**来源忠实度**有稳定改善
- 检索在标准 instruct 版上反而**引入了干扰项敏感性**
- **没有任何单一方法在 3B–4B 配置上对所有任务占优**

→ 弱模型的方法必须**按任务实测选**，不能照抄榜单。这也是 `model_profile.py` 强制 `--override-tier` 存在的原因。

### 四档手册

| | **S · 前沿旗舰** | **A · 主力** | **B · 轻量/中端** | **C · 小模型/边缘** |
|---|---|---|---|---|
| 代表（启发式） | Claude Opus 级 | Sonnet 级、推理型 R1/o 系列级 | Haiku 级、4o-mini 级、7B–70B 开源 | ≤8B、边缘部署 |
| **trust_selfcheck** | ✅ | ✅（基本） | ❌ | ❌ |
| 隔离验证 CoVe | ✅ 主力 | ✅ 主力 | ⚠️ 不可依赖 | ❌ 不用 |
| 自一致性 | ✅ 但见 §4 天花板 | ✅ 同上 | ⚠️ 不可依赖 | ❌ 不用 |
| 让模型自我反思 | 仅限隔离子任务内 | 仅限隔离子任务内 | **❌ 禁止**（实证有害） | **❌ 禁止** |
| 给模型资料（RAG/讲授证据） | ✅ | ✅ | ✅ **主力**（实证最有效） | ✅ 主力 |
| 单次声明上限 | 40 | 25 | 12 | 5 |
| 外部硬核查 | ✅ 兜底必做 | ✅ 必做 | ✅ **主力手段** | ✅ **唯一手段** |
| 人工闸门 | L2 时 | L2 时 | 建议常开 | 常开 |
| 单次 Shillcock 元认知提示 | 允许，用于生成验证问题 | 同左 | ❌ 禁止（会被当成反思触发编造） | ❌ 禁止 |

### 全档位共同的三条新禁忌（本轮新增）

1. ❌ **禁止把用户的引导性前提带进验证子任务**（§3）。这条对 S 档同样成立——谄媚不分强弱。
2. ❌ **禁止把"多次采样一致 / 多个 agent 一致"当成确认**。先查是否同源（§3），再查 §4 的天花板。
3. ❌ **禁止用"提醒自己不要谄媚"来对付谄媚。** 一手证据（Chandra et al.）显示：
   告知用户"模型可能谄媚"无济于事，而为了让回答显得谨慎而在句尾加免责声明同样无效。
   有效的是**中性重述 + 上下文隔离**这两步结构性动作，不是自我提醒。

### 一句收尾

> **模型越强，越可以让它帮忙核查；模型越弱，越要把判断权交给脚本。**
> **但无论强弱，"用户希望答案是什么"永远不能进入证据链。**

---

## 7. 本轮明确**不采信**的材料

搜索过程中大量出现、且已核实为不可用的内容，列出以免重复踩坑：

| 类型 | 为什么不采信 |
|---|---|
| 各型号"幻觉率 3%/6%/15–25%"对比表、TruthfulQA/HaluEval/SimpleQA 型号得分表 | 不同 SEO 来源互相矛盾，模型名也可能不存在；引用前必须回溯官方 system card |
| "某旗舰推理能力提升后幻觉减半"一类单点营销数字 | 无一手出处 |
| 对 HalluScan（arXiv 2605.02443）的转述出现两套互斥描述 | 一套说"4 个开源模型族 Llama-3.1-8B / Llama-4-Scout-17B / Qwen3-32B / GPT-OSS-20B"，另一套说"1.5–3B 紧凑模型、Self-Evaluation 池化 AUROC 0.688、6 种方法中 3 种出现分数方向反转"。**后者与 arXiv 摘要页冲突，不采用**；本套件只沿用摘要可核验的 ADR 2.0× 降本 / 0.1% AUROC 损失 / NLI 0.88 / HalluScore r=0.41 |
| "某场景里 A 模型安全 / B 模型不安全"类型号排序 | 二手，且样本构造差异大，跨机构不可比 |
