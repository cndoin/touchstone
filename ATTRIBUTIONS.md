# ATTRIBUTIONS · 出处与许可

本套件是**方法与思路的融合**，不包含任何第三方源代码。所有脚本均为本仓库原创（纯 Python 标准库）。

按本套件自己的规则，出处分三档标注：**一手可核验 / 二手转述（需回溯）/ 榜单快照（跨版本不可比）**。

---

## 1. 本仓库许可证

**MIT** —— 见 `LICENSE`。提示词、工作流、脚本均可自由使用、修改、再发布（含商用）。

---

## 2. 借鉴的开源项目（只借鉴思路，未引入代码）

| 项目 | 出处 | License | 借鉴了什么 | 可信度 |
|---|---|---|---|---|
| **FacTool** | GAIR-NLP（CMU / 上交 /  SJTU），github.com/GAIR-NLP/factool | Apache-2.0 | 五段式核查流水线骨架（claim extraction → query generation → tool querying → evidence collection → verification）；中间产物全留痕；claim 级 + response 级双指标 | 一手（仓库 README/论文） |
| **RefChecker** | amazon-science，arXiv 2405.14486，github.com/amazon-science/RefChecker | Apache-2.0 | 三元组粒度（subject, relation, object）；三种上下文设定 Zero/Noisy/Accurate | 一手（arXiv 编号 + 仓库） |
| **RefChecker（引用核查）** | markrussinovich（微软），arXiv 2607.00738，github.com/markrussinovich/refchecker | 见仓库 | **窄面硬核查**思路：把核查目标收敛到可判定的硬骨头（URL/DOI/引用/实体）；作者列表严重不符即判幻觉 | 一手（arXiv 编号） |
| **OpenFactCheck** | arXiv 2405.05583 | 见仓库 | 三插槽可插拔架构（claim processor / evidence retriever / verifier）；snowballing hallucination、self-awareness of unknown knowledge 两个度量维度 | 一手（arXiv 编号） |
| **FActScore** | shmsw25/FActScore，EMNLP 2023 | MIT | 原子事实抽取 → 逐条支持性判定 | 一手（仓库） |
| **CoVe**（Chain-of-Verification） | Meta AI，arXiv 2309.11495 | 论文 | **factored 验证**（上下文隔离）—— 本套件有效性的关键；"筒仓知识悖论"（拆分是白捡的准确率） | 一手（arXiv 编号） |
| **SelfCheckGPT** | arXiv 2303.08896 | 论文 | 零资源采样一致性检测 | 一手（arXiv 编号） |
| **verify-gate** | svy04/ballast | 见仓库 | 五标签体系 `confirmed/observed/assumed/hearsay/unknown`；**先证伪**；≥2 独立一手源；样本量；边界；90 天过期；"Task done" 也要过闸 | 一手（skill 文件） |
| **verification-gate** | jamie-bitflight / claudekit | 见仓库 | 执行类声明的强制证据要求 | 一手（skill 文件） |
| **Cleanlab TLM** | github.com/cleanlab/cleanlab-tlm（客户端 MIT，需 API key） | MIT（客户端） | **反例解释**机制：给"另一个合理答案是 X"比给 0.03 分有用得多 | 一手（仓库）；机制描述属可核验 |
| **Anthropic 官方《减少幻觉》指南** | Anthropic 官方文档 `platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations`（v3.4 回溯核验：URL 已从 docs.claude.com 迁移到 platform.claude.com） | 允许说"我不知道"；长文档先逐字抽取引文；用引文验证每条论断，无支撑则撤回并留 `[]` | 一手（官方文档全文） |

### v3.4 补充：厂商一手做法与诱导型幻觉（2026 H2）

| 来源 | 编号 / 出处 | 借鉴了什么 | 可信度 |
|---|---|---|---|
| **Why Language Models Hallucinate** | OpenAI 官网 2025-09-05；arXiv 2509.04664（Kalai, Vempala, Nachum, Zhang, Robinson, Jain, Mitchell, Beutel, Heidecke） | 幻觉 = 预训练侧任意低频事实 + 评测侧奖励猜测。**本地重建反向激励**的理论依据；SimpleQA 弃权/错误对照表 | 一手（官网原文 + arXiv 编号） |
| **Reduce hallucinations** | Anthropic 官方文档 `platform.claude.com/docs/en/test-and-evaluate/strengthen-guardrails/reduce-hallucinations`（旧 `docs.claude.com` 已 301） | 允许说不知道；>20k tokens 先逐字抽引文；无支撑引文即撤回并留 `[]`；external knowledge restriction | 一手（官方文档全文） |
| **Sycophantic AI decreases prosocial intentions and promotes dependence** | *Science* 391(6792)，DOI 10.1126/science.aec8352；预印本 arXiv 2510.01395 | **诱导型幻觉**：肯定用户比人类多 49%；造成伤害的特征正是驱动留存的特征 | 一手（卷期 + DOI）；其中 51%/47% 两个细分为二手转述 |
| **Sycophantic Chatbots Cause Delusional Spiraling, Even in Ideal Bayesians** | arXiv 2602.19141（Chandra, Kleiman-Weiner, Ragan-Kelley, Tenenbaum，MIT CSAIL） | 告知用户与禁止造假两种缓解均失效 → 只能靠**中性重述 + 隔离**做结构性防御 | 一手（arXiv 摘要） |
| **Confidently Wrong** | arXiv 2607.11414（Richard Zhe Wang，2026-07-13） | 自一致性天花板：**限定域**——在 FinQA（金融 QA）上，8/8 采样一致的答案仍有 15–23% 错；模型为 Qwen3-8B / Llama-3.1-8B / Gemma-2-9B。**摘要确认采用 15–23%，二手转述的 5–19% 不采用** | 一手（arXiv 摘要原文）；存在二手冲突已标注并以一手为准 |
| **Neuro-symbolic PRM** | arXiv 2608.26329（Yuxin Zi, Cong Xu, Suparna Bhattacharya, Martin Foltin, Amit Sheth，2026-08-26） | 借鉴「符号有效性 V + 语义接地 G」双层拆分与 **CSP 反事实符号扰动**思路；本套件第②层「工具成功 ≠ 算对」的直接理论来源 | 一手（arXiv 摘要原文） |
| **Soohak** | arXiv 2605.09063（Guijin Son et al.，2026-05-09，v3） | 借鉴其 **refusal 子集**设计思路与「拒答不随规模/测试时计算扩展」的结论；本套件病态题前置闸门的实证依据 | 一手（arXiv 摘要原文） |
| **From Accuracy to Robustness** | arXiv 2505.22203（EMNLP 2026 Main，Yuzhen Huang et al.） | 借鉴「规则式漏判 / 模型式被奖励黑客」二分，及「分类准确率 ≠ 抗黑客能力」结论 | 一手（EMNLP 2026 摘要原文） |
| **More Convincing, Not More Correct** | arXiv 2607.05904（Chenyu Zhou，2026-07-07） | 借鉴 **commit-first 去锚定**（裁判先自立作答）；本项目铁律 2「隔离验证」在数学域的形态 | 一手（arXiv 摘要原文） |
| **Ask, Condition or Abstain（ACA-RL）** | arXiv 2608.16554（EMNLP 2026，Yongqi Tong et al.） | 借鉴「追问 / 条件化 / 拒答」三选与 Missing-Premise Benchmark 的设计视角 | 一手（EMNLP 2026 摘要原文） |
| **Answering the Unanswerable** | arXiv 2508.18760；AAAI 2026，DOI 10.1609/aaai.v40i38.40496 | 借鉴「内部认知与外部回应错位」的诊断，说明闸门目标是逼出已有信号而非教新知识 | 一手（arXiv 摘要 + AAAI DOI） |
| **VeriFin** | arXiv 2608.10213（Bethel Hall, Sachi Shome, William Eiers，2026-08-10） | 借鉴「操作数绑定源事实 + Z3 判定 + 不可满足核定位」的数值核查范式（零误收） | 一手（arXiv 摘要原文） |
| **AI-Driven Formal Proof Search** | arXiv 2605.22763（DeepMind，George Tsoukalas et al.，2026-05-21） | 借鉴「形式化证书是唯一绝对保证」的定位与成本量级判断 | 一手（arXiv 摘要原文） |
| **Automated Conjecture Resolution** | arXiv 2604.03789（Haocheng Ju et al.，2026-04-04） | 借鉴 Rethlas + Archon「非形式推理 agent + 形式验证 agent」双 agent 流水线（与本套件隔离原则同构） | 一手（arXiv 摘要原文） |
| **Tool-Integrated RL** | arXiv 2608.28447（Minghui Xu, Zi Wang，2026-08-28） | 借鉴「计算错误占失败相当比例」的量化与工具集成的收益量级 | 一手（arXiv 摘要原文） |
| **SOS Certificates** | arXiv 2608.00326（Bohan Chen et al.，2026-07-31） | 借鉴「精确可校验输出」形态（展开比对系数即可验证） | 一手（arXiv 摘要原文） |
| **Diversion Decoding** | arXiv 2607.10476 | 比语义熵便宜 ~2.8× 且不弱的不确定性估计 | 一手（arXiv HTML 结果表） |
| **When Small Models Are Right for Wrong Reasons** | arXiv 2601.00513（AAAI 2026 TrustAgent Workshop） | 小模型 self-critique 有害、RAG 有益；外部/蒸馏验证器替代自反思 | 一手（arXiv 摘要） |
| **Scaling Down Hallucinations** | ICCSA 2026，DOI 10.1007/978-3-032-30488-9_39 | 紧凑模型上无单一方法全任务占优 → 方法必须按任务实测 | 一手（ACM DL 书目记录） |
| **2026 AI Index** | Stanford HAI，2026-04-13，Responsible AI 章 | 26 前沿模型谄媚诱导型幻觉率 22%–94% | **二手**，引用型号数字前必须回溯原文 |

### v3 补充：评测/红队与编码安全

| 项目 | License（**二手，以仓库 LICENSE 为准**） | 借鉴点 |
|---|---|---|
| **Promptfoo** | MIT | YAML + CLI 的 prompt 回归与**红队/对抗测试**（40+ 攻击类别转述，二手）；本套件在测试理念上对齐：把幻觉案例做成可执行回归集 |
| **hallucination-guard**（rune-kit，LobeHub 索引） | 见仓库 | **编码幻觉的同类实现**：提取 imports → 内部路径 Glob 校验 → 外部包 registry 校验（npm view / pip index）→ 导出符号 Grep → typosquat 编辑距离。本套件的 `dep_guard.py` 与之同源，并补了**新包特征（首版时间 <90 天）**与**跨生态防误报** |
| Cleanlab TLM | 客户端 MIT | 已在 v2 借鉴：反例解释 |

**slopsquatting 相关报道（全部二手，引用前回溯）**：
`huggingface-cli` 案例、`react-codeshift` 扩散 237 仓库、AI 生成代码包幻觉率约 19.7%（USENIX 研究转述）、
仅约 13% 幻觉包名属于近似拼写（因此相似度启发式常失效）。

### 检测器与框架（了解即可，本套件未引入）

| 项目 | License | 说明 |
|---|---|---|
| Vectara HHEM | 开源（HuggingFace） | 事实一致性 NLI 打分 |
| Patronus Lynx | 开源（+商业） | NLI 忠实度判定 |
| DeBERTa-NLI | 开源（HuggingFace） | 轻量蕴含判断 |
| DeepEval / Ragas / TruLens / Langfuse / Giskard / Promptfoo | 各自开源许可 | 评测与可观测（CI 侧） |
| Guardrails AI / NeMo Guardrails / Outlines / Instructor | 各自开源许可 | 护栏与结构化输出约束 |

> 上表的 License 来自各仓库 README/索引页转述，**属二手**；商用前请以仓库内 LICENSE 文件为准。

---

## 3. 参考论文

| 年份 | 论文 | 编号 / 出处 | 贡献 | 可信度 |
|---|---|---|---|---|
| 2023 | Chain-of-Verification Reduces Hallucination in LLMs | arXiv 2309.11495（Meta AI） | CoVe 四步法；factored 验证 | **一手**（arXiv 编号可核验） |
| 2023 | SelfCheckGPT: Zero-Resource Black-Box Hallucination Detection | arXiv 2303.08896 | 采样一致性检测 | 一手 |
| 2023 | FActScore: Fine-grained Atomic Evaluation | Min et al., EMNLP 2023 | 原子事实精度评估 | 一手 |
| 2024 | DoLa: Decoding by Contrasting Layers | Chuang et al., ICLR 2024 | 层间对比解码（原理借鉴：内部一致性分歧 = 危险信号） | 一手 |
| 2024 | Detecting Hallucinations Using Semantic Entropy | *Nature* 630:625-630（Farquhar et al., Oxford） | 语义层不确定性估计 | 一手 |
| 2024 | A Comprehensive Survey of Hallucination Mitigation Techniques | arXiv 2401.01313 | 32+ 方法分类法 | 一手 |
| 2025 | **Why Language Models Hallucinate** | arXiv 2509.04664（Kalai, Nachum, Vempala, Zhang / OpenAI） | 幻觉 = 二分类错误；评测惩罚弃权是根因 | 一手 |
| 2025 | FACTS Benchmark Suite | DeepMind + Kaggle（2025-12） | 四维度事实性评测 | 一手（官方博客）+ **榜单快照**（跨版本不可比） |
| 2026 | **Hallucinations Undermine Trust; Metacognition is a Way Forward** | arXiv 2605.01428（Yona, Geva, Matias / Google Research + TAU），ICML 2026 Position Track | confident error 重定义；忠实不确定性；AUROC 0.70–0.85；实用性税 | 一手 |
| 2026 | **Hyper-RAG**（超图增强 RAG） | 清华高跃团队等，*Nature Communications*（2026-06 报道） | 高阶关联建模 | 一手（期刊）+ 效果数字属**二手转述**，需回溯原文 |
| — | RAG-MCP: Mitigating Prompt Bloat in LLM Tool Selection | arXiv 2505.03275 | 工具池膨胀导致选择准确率暴跌 | 一手；具体百分比属二手转述 |
| — | Reducing Tool Hallucination via Reliability Alignment | arXiv 2412.04141 | 工具幻觉分类（selection vs usage） | 一手 |
| 2026 | **HalluScan** | arXiv **2605.02443**（2026-05） | ADR 自适应检测路由；NLI Verification 最优 | **二手**（数值需回溯原文；编号一手） |
| 2026 | **LLM Ghostbusters**（包幻觉 / Adaptive Unlearning） | arXiv 2605.01047 | 代码生成中的包幻觉是独立高发类别；包幻觉率降 81%（**二手**） | 编号一手 |
| 2026 | **LaaB**（Logical Consistency as a Bridge） | arXiv 2605.03971，ACL 2026 Main | 逻辑一致性作为检测信号 | 编号一手；结论二手 |
| 2026 | **BALTO** | arXiv 2606.15893 | claim 级验证投影到 token 级信用分配；证明 claim 级粒度优于 response 级 | 一手（arXiv 摘要页） |
| 2026 | **HalluGuard** | arXiv 2601.18753 | 风险分解为数据驱动 / 推理驱动；NTK 几何统一检测 | 编号一手；结论二手 |
| 2026 | 视觉源幻觉（多模态） | arXiv 2609.00231 | 多模态幻觉不仅来自语言先验，也来自视觉特征与图文对齐 | 一手（arXiv 摘要页） |
| 2026 | OpenHalDet | arXiv 2606.06959 | 17 数据集 × 16 检测器统一评测；无通用最优检测器 | 一手（编号） |

---

### v3.3 补充：厂商官方口径与标准机构（模型适配层依据）

| 来源 | 内容 | 可信度 |
|---|---|---|
| **NIST Generative AI Profile** | 将 **confabulation** 定义为"自信呈现的错误内容"；明确警告**生成的引用本身可能是编造的**；建议组合使用原始证据核查 + 治理 + 内容溯源 + 部署前测试 + 事件披露 | **一手**（NIST 官方出版物） |
| **OpenAI 帮助中心 / GPT-5 system card** | 官方承认 ChatGPT 会产出错误事实、编造引用与参考文献；Search 引用可能不完整/过时/错误，重要声明需自行溯源；产品会在模型间路由，benchmark 不一定匹配实际拿到的模型 | 官方口径（帮助中心/system card 为一手；具体百分比为**二手**） |
| **Anthropic：Citations API / Extended Thinking / Tool Use** | 原生引用：把声明锚定到源文档 char/page/content-block 区间；官方建议"材料里没有就明确拒答"，否则模型会用通用知识填空 | 官方文档（一手）；本仓库文档中的型号支持度为**转述** |
| **Anthropic 对幻觉三来源的归纳** | 记忆覆盖不足（长尾/新近/专业库）、组合错误（知道 A 与 B 拼成 A×B）、谄媚（跟随用户错误前提） | 二手教程转述，与官方口径一致 |
| **Google：Grounding with Google Search** | 检索 grounding + 结构化输出 | 官方（一手） |

**明确未采信的数据（引用前必须回溯官方原文）**：
2026 年多篇二手博客给出的型号级幻觉率与准确率（如"某型号幻觉率 15–25%""某型号事实错误减少 68%""TruthfulQA/HaluEval/SimpleQA 各型号得分表"等）
—— 这些数字在不同来源间**互相矛盾**，且多为产品宣传口径，本套件**不引用、不采信**。
需要时请以厂商官方 system card / model card 为准，并注明测试配置（是否开联网、哪个变体、对比组、测试日期）。

---

## 4. 数据集与基准（建回归集用）

**总索引**：`siyaqi/Awesome-Hallu-Eval`（GitHub）

- 通用：HaluEval、RAGTruth、FaithBench、HalluLens（Meta FAIR）、SimpleQA、TruthfulQA、FACTS、AA-Omniscience
- 中文：ANAH（OpenCompass）、Chinese SimpleQA、HalluQA（OpenMOSS）、UHGEval（IAAR-Shanghai）、C-FAITH（PKU-YuanGroup）、Bi'an（NJUNLP）、ChineseFactEval（GAIR-NLP）
- 垂直：LegalHallu、MedHalt、MedHallu、ToolBeHonest（工具调用）、Collu-Bench（代码）、BAMBOO（长上下文）
- 元评测：TRUE、AGGREFACT、FELM、SummEval、BEGIN、FaithDial

> 各数据集规模数字来自仓库/索引页转述，**属二手**，正式引用前请回溯仓库 README。

---

## 5. 数据可信度分档（本套件内部规则）

| 档位 | 处理规则 |
|---|---|
| **一手可核验** | 可直接引用，注明出处（arXiv 编号 / 期刊 / 官方文档 / 工具实际输出） |
| **二手转述** | **必须回溯一手**；回溯不到 → 标 `hearsay` 并点名出处，或标 `unknown` |
| **榜单快照** | 注明版本号与日期；跨版本不可比 |

本套件中明确标注为**二手、需回溯**的数据：
- "RAG 降幻觉 30–70%"、"GraphRAG 62%"、"Hyper-RAG 幻觉 −48.5%"
- "保险理赔场景含幻觉输出 9% → 2.2%，代价 +300–800ms"
- "腾讯混元 12.5% → 5.4%"、"Stanford 法律 AI 幻觉率 17–34%"
- "HalluScan：ADR 成本降 2.0×、AUROC 降 0.1%、NLI AUROC 0.88"
- "微软 refchecker 约 $0.04/篇；2025 NeurIPS/USENIX 约 1/20 论文含 ≥2 条幻觉引用"
- "微软 RefChecker 的 2025 NeurIPS 实测比例"

**这些数字进入正式产出前必须回溯原始出处。查不到就标 `unknown`。**

---

## 6. 商标与署名

- 本套件与上文提到的任何项目/机构**无隶属关系**，仅为方法论层面的借鉴与致谢。
- 引用本套件的方法时，建议同时引用上表对应的原始论文与项目——方法不是我们发明的，我们只做了工程化整合。
