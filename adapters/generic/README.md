# 通用 Harness 适配（Codex / Cursor / Cline / Roo / Gemini CLI / 自研 Agent）

没有 hooks 机制的宿主，用**规则文件 + 收尾脚本**两套补齐。

---

## 1. 规则文件放哪

| 宿主 | 文件位置 |
|---|---|
| Codex CLI | `AGENTS.md`（项目根） |
| Cursor | `.cursor/rules/touchstone.mdc` 或 `.cursorrules` |
| Cline | `.clinerules/touchstone.md` |
| Roo Code | `.roo/rules/touchstone.md` |
| Gemini CLI | `GEMINI.md` |
| Continue | `.continue/rules/touchstone.md` |
| OpenHands | `microagents/touchstone.md` |
| 自研 Agent | 塞进 system prompt 或工具描述 |

**不要全量塞 `SKILL.md`**。长 prompt 反而使错误 +10%。只放四段：铁律 + 红线 + 启动三问 + 输出契约。细节按需读 `references/`。

---

## 2. AGENTS.md 片段（可直接复制）

```markdown
## 反幻觉约定（touchstone）

铁律：
1. 无源即删 —— 找不到支撑的声明，删除并留 []，不许润色过去。
2. 验证必须隔离 —— 核查时用新的独立请求/子 agent，禁止把草稿带进核查上下文。
3. 先证伪再证实 —— 升级为 confirmed 前先主动找反证。
4. "做完了"也是声明 —— 文件存在？测试真过？命令真跑过？没验证不能说完成。
5. 可判定的先查 —— URL/DOI/实体/API/文件/版本/命令输出，能 100% 查，先啃。
6. 大项目里记忆不是证据 —— 陈述代码库现状前必须实际读文件或跑命令。
7. 工具失败 ≠ 通过 —— 记为 unverified。

红线（禁止编造，须核实后才可输出）：
URL · DOI · 论文标题与作者 · 法律条文 · 统计数据 · API 名称与参数 ·
文件路径 · 命令输出 · 版本号 · 人名与头衔 · 日期 · 价格 · 配置项名 · 数据库列名

启动三问：
Q1 上下文设定？ Accurate（有唯一权威原文）/ Noisy（RAG·多文档）/ Zero（无资料，必须检索）
Q2 风险等级？   L0 闲聊创意 / L1 业务·编码·报告 / L2 法律·医疗·金融·对外发布·不可逆操作
Q3 有无可执行校验？ 有 → 跑 scripts/hardcheck.py

交付前（闸门）：
python scripts/claim_lint.py --input .touchstone/claims.json --min-level L1
非零退出码 = 不许交付。
```

---

## 3. 收尾脚本（没有 hooks 时的替代）

每个任务结束前跑（或挂到 CI）：

```bash
PY=python3          # Windows 用 python
DEH="<skill 安装路径>/touchstone"

python3 "$DEH/scripts/hardcheck.py" --batch .touchstone/checks.json
python3 "$DEH/scripts/claim_lint.py" --input .touchstone/claims.json --min-level L1
python3 "$DEH/scripts/ledger.py" check --root . --drift
python3 "$DEH/scripts/regression.py" --cases .touchstone/regression-cases.json
```

CI 里加一步即可获得近似 Claude Code hooks 的闸门效果。

---

## 4. 自研 Agent 的接入要点

1. **把核查做成独立请求** —— 新开一次 LLM 调用，只给验证问题 + 工具结果，不带草稿。这就是 CoVe 的 factored 验证。
2. **把闸门做成代码** —— 不要用 LLM 判断"是否通过"，用 `claim_lint.py` 判断（确定性）。
3. **把账本做成文件** —— 不要用向量库存"项目约定"，用 JSON 落盘，可 diff、可 code review。
4. **把度量做成日志** —— 每次核查输出一行 JSONL，长期可统计趋势。
5. **把子 agent 的报告当 hearsay** —— 独立验证后才升级标签。

---

## 5. 能力对照

| 能力 | Claude Code | DeepSeek(API) | Codex/Cursor 类 | 自研 |
|---|---|---|---|---|
| 强制闸门（hook） | ✅ | ❌（靠调用方） | ⚠️ 部分 | ✅ 自己写 |
| 子 agent 上下文隔离 | ✅ | ✅ 多请求 | ⚠️ 视实现 | ✅ 独立请求 |
| 脚本执行 | ✅ | ❌（靠调用方） | ✅ | ✅ |
| 项目规则文件 | ✅ CLAUDE.md | ➖ | ✅ AGENTS.md/.mdc | ✅ |
| logprobs 取置信度 | ❌ | ⚠️ 以官方为准 | ❌ | 视接入方 |

方法论完全一致，只有 enforcement 强度不同。
