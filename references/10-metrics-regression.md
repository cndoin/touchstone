# 10 · 度量与回归集

> 不度量就不知道有没有用。改 prompt、改流程之后必须跑回归，防止按下葫芦浮起瓢。
> 指标来源：FacTool（claim/response 级）、TruLens（组件归因）、OpenAI 2509.04664（弃权率）、OpenFactCheck（滚雪球/自知力）、微软 RefChecker（引用可解析率）、verify-gate（执行声明未验证率）

---

## 1. 八个核心指标

| 指标 | 定义 | 怎么看 |
|---|---|---|
| **claim 级事实性** | 有源声明数 / 总声明数 | 低于 0.8 说明裸奔声明太多 |
| **response 级事实性** | 无幻觉回答数 / 总回答数 | 最直观的质量指标 |
| **弃权率 / 不确定性表达率** | 说"不知道/未验证"的比例 | **太低 = 在硬猜**（健康区间 5–20%） |
| **无源声明率** | 无 sources 却以事实口吻呈现的比例 | 应趋近 0 |
| **RAG 静默失败率** | 检索为空仍作答的比例 | 应趋近 0 |
| **引用可解析率** | 硬核查通过数 / 硬核查总数 | 应 = 100% |
| **执行声明未验证率** | 声称完成但无证据的比例 | 应 = 0 |
| **用户纠错数** | 用户明确指出错误的次数 | 趋势必须向下 |

### 两个高阶指标（OpenFactCheck）

- **滚雪球式幻觉率（snowballing）**：一个错引发一串错的比例。大项目里尤其危险——早期一个小错误会被后续所有步骤当成前提。
- **对未知的自知力（self-awareness of unknown knowledge）**：面对自己不知道的问题，能否承认不知道。直接对应弃权率。

### 组件归因（TruLens）

出错时要能分清是谁的锅：

| 归因 | 说明 | 对策 |
|---|---|---|
| **检索失败** | 证据没找到 | 改检索策略（混合检索 + rerank + 相关性阈值） |
| **生成失败** | 证据在上下文里但模型没用 | 改流程（引用先行 + 原子化 + 隔离验证） |
| **源本身错误** | 忠实但错误 | 换源 / 交叉验证 |

---

## 2. 回归集建设

### 最小可行回归集（先建这个）

每次线上出错，加一条。**不要等做大了再开始。**

```json
{
  "id": "case-001",
  "date": "2026-09-16",
  "source": "真实出错记录",
  "prompt": "用户当时的原始提问（脱敏）",
  "bad_output": "当时的错误输出",
  "error_type": "knowledge|tool|param|evidence|action",
  "why_wrong": "为什么错（编造了什么）",
  "expected_behavior": "正确行为应该是（说不知道 / 去检索 / 给出正确来源）",
  "check": {
    "type": "must_contain|must_not_contain|must_abstain|must_have_source",
    "value": "..."
  }
}
```

### 跑回归

```bash
PY=python3          # Windows 用 python
python3 scripts/regression.py --cases assets/regression-cases.json
```

脚本会对每条 case 输出 PASS / FAIL / SKIP，并汇总：

```
总case: 12  PASS: 10  FAIL: 1  SKIP: 1
按类型：knowledge 4/5  action 3/3  tool 3/3
```

**SKIP 不等于 PASS**——无法自动判定的 case 需要人工过一遍，脚本会明确标出来。

---

## 3. 可借用的公开基准

**通用**：HaluEval（35k）、RAGTruth（2.97k）、FaithBench（750）、HalluLens（Meta FAIR，130k）、SimpleQA、TruthfulQA、FACTS、AA-Omniscience

**中文（做中文项目必用）**：

| 数据集 | 出处 | 规模 |
|---|---|---|
| ANAH | OpenCompass | 4.3k 生成（中/英） |
| Chinese SimpleQA | he-yancheng | 10k 问题 |
| HalluQA | OpenMOSS | 450 问题 |
| UHGEval | IAAR-Shanghai | 5k 中文新闻 |
| C-FAITH | PKU-YuanGroup | 4k 中文摘要 |
| Bi'an | NJUNLP | 5.2k 三元组 |
| ChineseFactEval | GAIR-NLP | 125 prompts |

**垂直**：LegalHallu（745k，法律）、MedHalt（25.64k）/ MedHallu（10k，医疗）、ToolBeHonest（700，工具调用）、Collu-Bench（1.2k，代码）

**总索引**：`siyaqi/Awesome-Hallu-Eval`（GitHub）

> 规模数字来自仓库/索引页转述，**属二手数据**，正式引用前请回溯仓库 README。

---

## 4. 量级目标（工程参考）

| 参照 | 数据 |
|---|---|
| 事实核查网关（2026 工程实践） | 含幻觉输出 **9% → 2.2%**，代价 +300–800ms（二手转述，需回溯） |
| 微软 refchecker 成本 | 约 **$0.04/篇** 引用核查 |
| FActScore 成本 | 约 **$1/100 句** |

**本套件应达到的量级**：把"无源声明率"和"执行声明未验证率"压到 0，把"引用可解析率"拉到 100%。这两个是**能做到 100% 的**，先把它们做到位，再去追求降低事实错误率。

---

## 5. 度量落地的最小动作

不用上全套可观测性平台，先做三件事：

1. **每次交付输出 claims JSON**，落盘到 `.touchstone/claims-<date>.json`
2. **跑 claim_lint.py**，把结果（通过/失败/各字段统计）记到 `.touchstone/metrics.md`
3. **每次出错加一条回归 case**，每月跑一次全量回归

有了这三样，就能看出趋势；否则所有改进都是凭感觉。
