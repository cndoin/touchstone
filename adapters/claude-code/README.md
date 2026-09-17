# Claude Code 适配

Claude Code 是本套件能拿到**最强强制力**的宿主：hooks（硬闸门）+ 子 agent（上下文隔离）+ Bash（脚本执行）三者齐全。

---

## 1. 安装

```bash
SKILL_SRC="<本 skill 包路径>/touchstone"

# 项目级（推荐大项目用这个，可随仓库提交）
mkdir -p .claude/skills
cp -r "$SKILL_SRC" .claude/skills/

# 用户级（所有项目生效）
mkdir -p ~/.claude/skills
cp -r "$SKILL_SRC" ~/.claude/skills/
```

> skill 目录与加载机制以 Anthropic 官方文档为准（docs.claude.com），版本间有差异。

---

## 2. 装 hooks（这一步才把它从"提示词"变成"闸门"）

把 `settings-hooks.json` 的内容合并进 `.claude/settings.json`（项目级）或 `~/.claude/settings.json`（用户级）。

| Hook | 脚本 | 治什么 |
|---|---|---|
| `Stop` | `hooks/verify_gate.py` | **行动幻觉**：声称完成但没证据 → 要求补证据 |
| `SubagentStop` | `hooks/subagent_gate.py` | **子 agent 自述**：报告含"已完成/已验证"却无证据 → 拦截补证据 |
| `PreCompact` | `hooks/precompact_snapshot.py` | **记忆漂移**：压缩前把账本/执行声明/git 状态落盘，压缩后可读回 |
| `PreToolUse(Bash)` | `hooks/guard_bash.py` | **不可逆操作**：`rm -rf /`、`git push --force`、`DROP TABLE`、下载即执行 |
| `PostToolUse(Write/Edit)` | 内联单行 | 写完确认文件真的落盘 |

### ⚠️ 两个官方语义坑（不绕开，闸门会失效或卡死用户）

**坑 1：Stop hook 连续阻断 8 次后，Claude Code 会覆盖 hook 强制结束回合。**
一味 exit 2 的闸门在第 8 次就失效了。`verify_gate.py` 的三级降级：

```
第 1~N-1 次  → exit 2 强阻断（Claude 回来补证据）
检测到 stop_hook_active=true 或接近上限
            → 输出 JSON hookSpecificOutput.additionalContext + exit 0
              （继续回合，但不计为阻断，不消耗 8 次额度）
达到硬上限（默认 6 次）
            → 写日志 + 放行，绝不把用户卡死
```

**坑 2：PostToolUse 的 exit 2 不能撤销已执行的工具。**
只有 `PreToolUse` / `Stop` / `SubagentStop` / `UserPromptSubmit` 能真正阻断。
`PostToolUse` 的 exit 2 只是把 stderr 回喂给模型——所以那个"确认文件落盘"的钩子只是提醒，不是拦截。

### 退出码约定

| 退出码 | Claude Code 的行为 | 本套件用法 |
|---|---|---|
| 0 | 放行 | 检查通过（或已降级为温和反馈） |
| 2 | **阻断**，stderr 回喂给模型 | 缺证据 / 命中高危命令 |
| 其他 | 非阻断错误 | 脚本异常（绝不用来阻断） |

### 稳定性设计

- `guard_bash.py`：**stdin 解析失败一律放行**。绝不能因为 hook 脚本的 bug 卡住正常工作。
- `verify_gate.py`：没有 `execution_claims.json` 时**不阻断**（很多任务本就没有执行声明），只提示。
- 临时放行高危命令：`TOUCHSTONE_ALLOW_DANGEROUS=1`。

---

## 3. 大项目：加 CLAUDE.md 约定

项目根 `CLAUDE.md` 加一段：

```markdown
## 反幻觉约定（touchstone）
1. 陈述代码库现状前必须实际读文件或跑命令；禁止"我记得……"。
2. 架构决策/命名约定以 .touchstone/ledger.json 为准；与代码冲突时以代码为准并更新账本。
3. 声称"已完成"必须写入 .touchstone/execution_claims.json 并附工具输出。
4. 不确定就说不确定，按风险路由（L0/L1/L2）决定投入。
5. 交付前跑 python scripts/claim_lint.py --input .touchstone/claims.json；非零退出码不许交付。
```

---

## 4. 子 agent 做隔离验证

Claude Code 的子 agent 天然独立上下文，正好对应 CoVe 的 factored 验证。

派发模板见 `assets/templates/verification-subtask.md`。三条硬要求：

1. **背景段只给定位信息，不给结论**（否则就是锚定）
2. **一条声明一个子 agent**，不要批量塞
3. **回收时默认标 `hearsay`**，独立验证后才升级

---

## 5. Claude Code 特有的坑

| 坑 | 对策 |
|---|---|
| 长会话 `/compact` 后早期细节丢失 | 压缩后**重新读关键文件**；关键约定放 `ledger.json` + `CLAUDE.md` |
| 子 agent 报告看起来很专业就信了 | 一律执行同闸验证 |
| 并行工具调用导致"以为做了" | 逐个检查返回值 |
| 自动接受编辑后没实际编译 | 声明完成前必须跑构建并贴输出 |
| hooks 配置错了静默失效 | 配置后手动触发一次（比如故意跑一条被拦的命令看是否拦住） |

---

## 6. 一键自查

```bash
python .claude/skills/touchstone/scripts/hardcheck.py --file ./README.md --offline
python .claude/skills/touchstone/scripts/claim_lint.py --input .touchstone/claims.json --min-level L1
python .claude/skills/touchstone/scripts/ledger.py check --root . --drift
```
