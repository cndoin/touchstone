# 11 · Harness 适配：Claude Code / DeepSeek / 通用 Agent

> 同一套方法论，不同宿主的执行机制不同。
> 原则：**方法论不变，落点随宿主变**。提示词约束放 skill 文件，强制约束放 hooks/脚本。

---

## 0. 三条宿主无关的原则

1. **能写成脚本的，不要写进 prompt。** Prompt 可被跳过，脚本不会。
2. **上下文隔离靠机制，不靠自觉。** 用子 agent / 独立请求 / 新会话，而不是"假装没看过草稿"。
3. **闸门放在宿主真正会执行的钩子上**（Claude Code = hooks；CI = pipeline step；其他 = 收尾脚本）。

---

## 1. Claude Code（重点适配）

### 1.1 安装

```bash
# 用户级（所有项目生效）
cp -r touchstone ~/.claude/skills/

# 项目级（只在本项目生效，推荐大项目用这个）
mkdir -p .claude/skills && cp -r touchstone .claude/skills/
```

Claude Code 会在匹配任务时自动加载 `SKILL.md`。

> 目录与加载机制以官方文档为准（docs.claude.com / Anthropic 官方仓库），版本间有差异。

### 1.2 用 hooks 做硬闸门（这是 v2 相对 v1 的关键升级）

在 `.claude/settings.json`（项目级）或 `~/.claude/settings.json`（用户级）里配置：

```jsonc
{
  "hooks": {
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/skills/touchstone/adapters/claude-code/hooks/verify_gate.py"
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "python3 .claude/skills/touchstone/adapters/claude-code/hooks/guard_bash.py"
          }
        ]
      }
    ]
  }
}
```

| Hook | 干什么 | 为什么重要 |
|---|---|---|
| **Stop** | 主 agent 要结束回合时，检查本次产出是否挂了证据 | 治"声称完成但没做"——最高危的一类 |
| **PreToolUse(Bash)** | 拦截不可逆/高危命令（rm -rf、git push --force、发布、外发） | 治行动幻觉 |
| **SubagentStop** | 子 agent 返回时校验其报告是否含证据 | 治回声幻觉 |

`verify_gate.py` 的行为（fail-closed）：
- 读取本次会话声明产出物的清单（由主 agent 写入 `.touchstone/execution_claims.json`）
- 逐条校验：文件是否存在、命令是否真跑过（有输出记录）
- 缺证据 → 退出码 1，并往 stderr 输出要求（Claude Code 会把 stderr 反馈给模型，让它补证据）

> 注意：hooks 的字段与事件名随版本变化，**以官方文档为准**，配置后务必手动触发一次验证。

### 1.3 用子 agent 做上下文隔离

Claude Code 的 Task/子 agent 天然是独立上下文——这正是 CoVe factored 验证需要的。

派发时的硬要求：

```
【独立核查 · 禁止参考主会话】
背景：{最小必要背景，不含任何结论性表述}
核查目标：{单个原子声明}
任务：
  1. 只针对该目标收集证据（读文件/跑命令/检索）
  2. 输出：结论(supported|contradicted|unverified) + 证据原文摘录 + 路径
  3. 禁止读取主会话的草稿或结论
  4. 找不到 → unverified，不要猜
```

**主 agent 侧**：子 agent 返回的结论默认标 `hearsay`，独立验证后才升级。

### 1.4 CLAUDE.md 里该放什么

项目根 `CLAUDE.md` 加一段（大项目强烈建议）：

```markdown
## 反幻觉约定（touchstone）
1. 陈述代码库现状前必须实际读文件或跑命令；禁止"我记得……"。
2. 架构决策/命名约定以 .touchstone/ledger.json 为准；与代码冲突时以代码为准并更新账本。
3. 声称"已完成"必须附工具输出（ls / 测试计数 / 构建输出）。
4. 不确定就说不确定，并按风险路由（L0/L1/L2）决定投入。
5. 交付前跑 scripts/claim_lint.py；非零退出码不许交付。
```

### 1.5 Claude Code 特有的坑

| 坑 | 对策 |
|---|---|
| 长会话后上下文被压缩（compact），早期细节丢失 | 压缩后**重新读关键文件**，不要依赖压缩摘要；关键约定放 `ledger.json` 和 `CLAUDE.md` |
| 子 agent 报告看起来很专业就信了 | 一律执行同闸验证 |
| 并行工具调用导致"以为做了" | 逐个检查返回值，不要假设成功 |
| 自动接受编辑后没实际编译 | 声明完成前必须跑构建并贴输出 |

---

## 2. DeepSeek（重点适配）

DeepSeek 系列（deepseek-chat / deepseek-reasoner）在使用上有几个必须调整的点。

> ⚠️ 具体参数（上下文长度、logprobs 支持、JSON Output / Function Calling 能力、温度范围）**以 DeepSeek 官方文档为准**，平台更新频繁，本套件不对具体数值做断言。

### 2.1 推理模型（reasoner / R1 类）的特殊处理

**推理链不是证据。** 长 CoT 会引入中间步骤的编造——研究表明复杂任务上 CoT 可能使幻觉 +12%，推理模型在长文本摘要上幻觉率反而更高。

适配规则：

1. **推理过程与最终结论分开对待**：最终结论必须独立过核查闸门，不能因为"推理看起来严密"就采信。
2. **不要让推理链充当引用**：链条里出现的 URL/论文/API 名，同样要过 `hardcheck.py`。
3. **显式要求输出证据段**：在系统提示里要求结构化输出 `结论 / 证据 / 来源 / 置信度`，把推理过程限制在单独字段。
4. **推理越长越要核查**：CoT 长度与幻觉率无负相关，不要因为"想了很久"就放松验证。

### 2.2 无 logprobs 时的置信度替代方案

如果当前接入的 DeepSeek 接口不提供 logprobs（很多部署如此），**不要假装能拿到**。改用黑盒手段：

| 手段 | 怎么做 | 工具 |
|---|---|---|
| **多次采样一致性** | 同问题采样 3–5 次，按语义聚类看是否收敛 | `scripts/selfcheck.py` |
| **语义熵**（*Nature* 2024, Farquhar et al.） | 在**语义层面**而非 token 层面算熵：把多次采样按"意思相同"聚类后算熵 | 同上（脚本做近似：字符/词面聚类） |
| **口头置信度（校准后）** | 让模型自报，但**绝不直接采信**——普遍过度自信 | 只用于路由，不用于免责 |

**关键提醒**：自一致性高 ≠ 正确。模型可能稳定地重复同一个错误。一致性低是"危险信号"，一致性高只是"及格线"。

### 2.3 中文场景的额外规则

DeepSeek 中文能力强，但中文互联网的二手资料密度极高，这反而提升幻觉风险：

1. **中文数字/百分比必须回溯一手**：中文技术博客里"据研究显示""官方称"的比例远高于英文源。
2. **优先官方源**：政府站点、标准原文、官方文档、arXiv/期刊原文、企业官网 changelog。
3. **中文论文/报告引用**：标题 + 作者 + 机构 + 年份 一起查，机构或作者不符即判幻觉。
4. **百科与聚合站一律当 `hearsay`**：需要一手源支撑才能升级。

### 2.4 系统提示片段（可直接贴）

```text
你在回答时必须遵守以下规则：
1. 事实性陈述必须给出来源（文件路径+章节、URL、或工具输出）。给不出的，删除或明确标注【推断】。
2. 禁止编造：URL、DOI、论文标题与作者、API 名称与参数、文件路径、命令输出、版本号、统计数据。
3. 未实际执行的操作，不得声称已执行。声称完成必须附工具输出。
4. 不确定时明确说"未找到可靠来源"或"这条我没把握"，并给出反证方向。说不知道是正确行为。
5. 你的推理过程不构成证据。最终结论里的每个可判定项（链接/版本/文件/API）必须单独核实。
6. 输出结构：结论 / 证据 / 来源 / 置信度(高|中|低|无) / 反例或反证方向。
```

### 2.5 DeepSeek 侧的检查清单

- [ ] 系统提示里带了"说不知道是正确行为"的反向激励？
- [ ] 最终结论与推理链分开，只对结论做核查？
- [ ] 置信度只用于路由（低置信 → 检索/交给人），不用于免责？
- [ ] 中文数字/引用都回溯了一手？
- [ ] 未依赖 logprobs；若依赖了，是否以官方接口能力为准？

---

## 3. 通用 Harness（Codex / Cursor / Cline / Roo / OpenHands / 自研）

没有 hooks 机制的宿主，用**规则文件 + 收尾脚本**两套补齐。

### 3.1 规则文件放置

| 宿主 | 文件 |
|---|---|
| Codex CLI | `AGENTS.md`（项目根） |
| Cursor | `.cursor/rules/*.mdc` 或 `.cursorrules` |
| Cline | `.clinerules/` |
| Roo Code | `.roo/rules/` |
| Gemini CLI | `GEMINI.md` |
| Continue | `.continue/rules/` |
| 自研 Agent | 把 `SKILL.md` 塞进 system prompt 或工具描述 |

规则文件内容 = 本套件 `SKILL.md` 的**铁律 + 红线 + 启动三问 + 输出契约**四段（不用全量塞，避免长 prompt 反效果——长 prompt 可使错误 +10%）。细节按需读 `references/`。

### 3.2 收尾脚本（没有 hooks 时的替代）

在每个任务结束时手动/自动跑：

```bash
PY=python3          # Windows 用 python
python3 scripts/claim_lint.py --input .touchstone/claims.json --min-level L1
python3 scripts/hardcheck.py --batch .touchstone/checks.json
python3 scripts/ledger.py check --root . --drift
```

CI 里加一步即可获得近似的闸门效果。

### 3.3 自研 Agent 的接入要点

1. **把核查做成独立请求**：新开一个 LLM 调用，只给验证问题 + 工具结果，不带草稿 → 这就是 factored 验证。
2. **把闸门做成代码**：不要用 LLM 判断"是否通过"，用脚本判断（确定性）。
3. **把账本做成文件**：不要用向量库存"项目约定"，用 JSON 落盘，可 diff、可 code review。
4. **把度量做成日志**：每次核查输出一行 JSONL，长期可统计。

---

## 4. 宿主能力对照表

| 能力 | Claude Code | DeepSeek(API) | Codex/Cursor 类 | 自研 |
|---|---|---|---|---|
| 强制闸门（hook） | ✅ hooks | ❌（靠调用方） | ⚠️ 部分 | ✅ 自己写 |
| 子 agent 上下文隔离 | ✅ Task | ✅ 多请求 | ⚠️ 视实现 | ✅ 独立请求 |
| 脚本执行 | ✅ Bash | ❌（靠调用方） | ✅ | ✅ |
| 项目规则文件 | ✅ CLAUDE.md | ➖ | ✅ AGENTS.md/.mdc | ✅ |
| logprobs 取置信度 | ❌ | ⚠️ 以官方为准 | ❌ | 视接入方 |

**结论**：Claude Code 能拿到最强的强制力（hooks + 子 agent + Bash 全都有），DeepSeek 侧重点在**提示词约束 + 推理链隔离**，通用宿主靠**规则文件 + CI 收尾脚本**。方法论完全一致，只是 enforcement 强度不同。
