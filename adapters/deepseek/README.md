# DeepSeek 适配

DeepSeek 侧没有 hooks 机制，**强制力必须由调用方（你的应用/agent 框架）提供**。
本目录给的是：提示词约束 + 调用侧流程 + 推理模型的专门处理。

> ⚠️ 关于具体能力（上下文长度、是否提供 logprobs、是否支持 JSON Output / Function Calling、temperature 取值范围），
> **一律以 DeepSeek 官方文档为准**。平台更新频繁，本套件不对具体数值做断言——这正是本 skill 反对的做法。

---

## 1. 推理模型（reasoner / R1 类）的专门处理

**核心原则：推理链不是证据。**

长 CoT 会引入中间步骤的编造。研究表明复杂任务上 CoT 可能使幻觉 +12%；推理模型在长文本摘要上的幻觉率反而更高（Vectara 榜单数据，二手，需回溯）。

| 规则 | 说明 |
|---|---|
| 推理与结论分离 | 把推理过程放进单独字段，最终结论独立过核查闸门 |
| 推理链里的引用不算数 | 链条中出现的 URL/论文/API 名，同样要过 `hardcheck.py` |
| 想得久 ≠ 更可靠 | 不要因为推理很长就放松验证；CoT 长度与幻觉率无负相关 |
| 结构化输出 | 强制输出 `结论 / 证据 / 来源 / 置信度 / 反例方向` 五段 |

### 调用侧模板

```python
# 伪代码：两段式调用，避免推理链污染结论
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},      # 见 system-prompt.md
    {"role": "user", "content": user_question},
]

resp = client.chat.completions.create(
    model="deepseek-reasoner",          # 以官方文档为准
    messages=messages,
    # temperature 不用来治幻觉：实证研究显示温度对幻觉率影响很小
)

# 关键：把结论里的可判定项抽出来，交给脚本实查
claims = extract_claims(resp.choices[0].message.content)
subprocess.run([PY, "scripts/hardcheck.py", "--batch", checks_json])   # fail-closed
subprocess.run([PY, "scripts/claim_lint.py", "--input", claims_json])  # 闸门
```

---

## 2. 没有 logprobs 时怎么估置信度

若接入的接口不提供 logprobs（很多部署如此），**不要假装能拿到**。用黑盒手段：

| 手段 | 做法 | 工具 |
|---|---|---|
| 多次采样一致性 | 同问题采样 3–5 次，语义聚类看是否收敛 | `scripts/selfcheck.py` |
| 语义熵（*Nature* 2024） | 语义层面而非 token 层面算熵 | 同上（近似实现） |
| 口头置信度 | 模型自报，**校准后再用** | 只用于路由，不用于免责 |

```bash
python scripts/selfcheck.py --samples samples.json
# 退出码：0=高一致(>=0.8)  2=灰区(0.6~0.8)  3=低一致(<0.6)
```

**边界**：一致性高 ≠ 正确。模型可以稳定地重复同一个错误。一致性低是危险信号，一致性高只是及格线。

---

## 3. 中文场景的额外规则

DeepSeek 中文能力强，但中文互联网二手资料密度极高，这反而**提升**幻觉风险：

1. **中文数字/百分比必须回溯一手**：中文技术博客里"据研究显示""官方称"的比例远高于英文源。
2. **优先官方源**：政府站点、标准原文、官方文档、arXiv/期刊原文、企业官网 changelog。
3. **中文论文/报告引用**：标题 + 作者 + 机构 + 年份 一起查，机构或作者不符即判幻觉。
4. **百科与聚合站一律当 `hearsay`**：需要一手源支撑才能升级为 `confirmed`。
5. **中文长文档（>20k tokens）**：先逐字抽取引文再作答（Anthropic 官方做法）。

---

## 4. 系统提示（见 `system-prompt.md`）

直接把 `system-prompt.md` 的内容作为 system message。它包含：
- 反向激励（说"不知道"是正确行为）
- 红线清单
- 五段式输出结构
- 推理链非证据声明

---

## 5. 调用侧检查清单

- [ ] system prompt 里带了"说不知道是正确行为"的反向激励？
- [ ] 最终结论与推理链分开处理，只对结论做核查？
- [ ] 结论里的可判定项（链接/版本/文件/API）跑过 `hardcheck.py`？
- [ ] 交付前跑过 `claim_lint.py`，非零退出码不放行？
- [ ] 置信度只用于路由（低置信 → 检索/交给人），不用于免责？
- [ ] 中文数字/引用都回溯了一手？
- [ ] 未依赖 logprobs；若依赖了，是否以官方接口能力为准？

---

## 6. 与 Claude Code 侧的差距（以及如何补）

| 能力 | Claude Code | DeepSeek 侧补法 |
|---|---|---|
| 强制闸门 | hooks | 调用方在返回给用户前跑 `claim_lint.py` |
| 上下文隔离 | 子 agent | 发起**新的独立请求**做核查，不带草稿 |
| 脚本执行 | Bash | 调用方执行 `hardcheck.py` |
| 项目账本 | 文件 + 命令 | 同样用 `ledger.py`，由调用方触发 |

方法论完全一致，只是 enforcement 的位置从宿主挪到了调用方。
