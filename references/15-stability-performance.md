# 15 · 稳定性与效率：特殊环境下不崩、不卡、不误判

> 目标：**运行一半出错**和**模型当掉**都要么不发生，要么以"明确降级 + 留痕"的方式发生。
> 核心原则：**fail-closed + 明确降级**。宁可说"未验证"，不可说"通过"，也不可崩溃。

---

## 1. 环境矩阵（每种环境怎么跑）

| 环境 | 表现 | 对策 |
|---|---|---|
| **无网络** | URL/DOI/registry 查不到 | `--offline` 直接跳过网络项；不离线时网络失败记为 `UNVERIFIED`（退出码 2），**不是通过** |
| **受限沙箱**（无线程池 / 无写权限） | 并发、缓存写入可能失败 | `map_parallel` 捕获异常自动退化为串行；缓存写入失败静默忽略 |
| **只读文件系统** | 写缓存/快照失败 | 全部 `try/except`，失败静默；只有"检查"失败才上报 |
| **Windows + GBK 控制台** | 中文输出炸掉 | 所有脚本 `sys.stdout.reconfigure(encoding="utf-8")` |
| **路径含中文/空格** | 命令拼接出错 | 全部用绝对路径 + `subprocess(shell=True)` 传原串；不手工拼引号 |
| **公司代理 / SSL 拦截** | HTTPS 证书错误 | 记为 `UNVERIFIED` 并给出错误类型，不假装成功 |
| **Python 3.8** | 新版语法不可用 | 只用 3.8+ 语法；无 f-string `=`, 无 `match`, 无 walrus 依赖 |
| **CI（无交互）** | 不能等人确认 | `--offline` + `--json` + 退出码驱动门禁 |

---

## 2. 效率机制（v3）

| 机制 | 参数 | 默认值 | 说明 |
|---|---|---|---|
| **缓存** | `--cache-dir` / `--no-cache` / `TOUCHSTONE_CACHE_DIR` | 系统临时目录，TTL 6 小时 | 同一 URL/DOI/包版本不重复查 |
| **并发** | `--jobs` | 4（上限 16） | 只并发网络项；文件/命令保持串行（有副作用，且顺序可预测） |
| **重试** | `--retries` | 1 | 只重试瞬时故障，且指数退避 |
| **预算** | `--max-checks` | 不限 | 防止一次性核查失控；超预算的项记为未验证并明确告警 |
| **原子写** | （默认） | — | 先写 `.tmp` 再 `os.replace`，不会留下半截 JSON |

**成本路由**（见 `06-cost-routing.md`）：便宜手段先跑，灰区才升级贵手段。
实测参考（HalluScan ADR，**二手数据需回溯**）：成本降 2.0×，AUROC 仅降 0.1%。

---

## 3. 不崩溃的六条实现纪律

1. **所有外部调用都有超时。** HTTP 默认 8s，命令默认 8s，hook 命令 60s。
2. **所有异常都收敛成状态，不向上抛。** 网络异常 → `UNVERIFIED`；解析失败 → `EXIT_USAGE` 并写明原因。
3. **hook 脚本解析失败一律放行。** 绝不因为脚本 bug 卡住用户正常工作。
4. **stdout 只放数据，人类提示走 stderr。** 方便下游解析，也避免污染 JSON。
5. **退出码语义统一。** 0=通过 / 1=失败 / 2=未验证 / 3=用法错误（`selfcheck.py` 例外：0/2/3 表示一致性档位）。
6. **任何"跳过"都要留痕。** `SKIP` ≠ `PASS`，回归脚本会明确列出来要求人工过。

---

## 4. 模型侧的稳定性（防"当掉"）

| 风险 | 表现 | 对策 |
|---|---|---|
| 超长上下文 | 早期细节丢失 → 凭模糊记忆作答 | 引用先行（>20k tokens 先抽引文）；PreCompact 快照；账本落盘 |
| 上下文压缩 | 约定被"记错" | `precompact_snapshot.py` + 压缩后**先读文件再开口** |
| 子 agent 级联失败 | 一个错传一串 | 子 agent 报告默认 `hearsay`；`subagent_gate.py` 要求带证据 |
| 无限阻断循环 | Stop hook 一直不放行 | 阻断计数上限（6 次）+ `stop_hook_active` 检测 + 超限放行并留痕 |
| 工具批量失败 | 静默当通过 | 工具失败 = `unverified`，绝不默认通过 |
| 核查本身拖垮任务 | 核查比干活还慢 | 预算上限 + 成本路由 + 缓存 |

---

## 5. CI 集成

```yaml
- name: touchstone gate
  run: |
    python scripts/pipeline.py --root . \
      --checks .touchstone/checks.json \
      --claims .touchstone/claims.json \
      --offline --json --report gate-report.json
  # 退出码 1 = 不许合并；2 = 有未验证项（可配为警告）
```

完整示例见 `assets/ci/github-actions.yml`。

---

## 6. 三套测试（怎么验证"真的稳"）

| | `selftest.py` | `robustness_test.py` | `stability_test.py` |
|---|---|---|---|
| 定位 | 快速冒烟 | 深度健壮性 | 工程一致性 |
| 用例 | 38 条 | 70 条 | 99 条 |
| 覆盖 | 正常路径 + 关键失败路径 | 边界 / 异常 / 编码 / 并发 / 性能 / 幂等 / 极端参数 | 编译 / 幂等 / 并发写 / 垃圾输入 / 环境（GBK·离线·只读·非 ASCII 路径）/ 文档与版本一致性 / 资产合法性 / 安装目录同步 |
| 耗时 | 秒级 | 几十秒 | 几分钟 |
| 何时跑 | 每次改动后 | 发版前、换环境后 | 发版前（动过 hook、文档或版本号后必跑） |

```bash
python scripts/selftest.py          # 秒级冒烟
python scripts/robustness_test.py   # 深度：70 条
python scripts/robustness_test.py --only=extreme,perf   # 只跑某几组
python scripts/stability_test.py    # 工程一致性：99 条
python scripts/stability_test.py --no-install-check      # 跳过安装目录比对
```

**stability_test 抓的是"另一类烂掉"**：前两套都在测脚本行为，但一个技能包还会以别的方式坏——
hook 被改出 `IndentationError`、文档里的版本号和 `VERSION` 文件对不上、
文档里写的引用路径（`references/` 下某个文件）其实不存在、工作区改完了忘了同步到安装目录。
这四类都曾在真实开发中出现过，且**前两套测试一条都抓不到**（v3.4.1 实测）。

**robustness_test 的断言设计**（比"结果对不对"更关键）：

1. **绝不出现 Traceback** —— 任何输入下脚本都不能崩（捕获 stderr 里的异常栈）
2. **退出码必须落在 {0,1,2,3}** —— 越界即失败
3. **`--json` 输出必须可解析** —— 下游要能吃
4. **幂等** —— 同样输入跑两次，退出码与输出完全一致
5. **性能预算** —— 200 文件目录检查 < 5s；1000 条声明 lint < 10s

覆盖的刁钻输入：GBK 文件、UTF-8 BOM、空文件、>2MB 大文件、二进制文件、
中文+空格路径、50 层嵌套目录、`node_modules`、损坏 JSON、字段类型全错的契约、
5 进程并发写同一缓存目录、写坏的缓存文件、`--timeout 0`、`--max-checks -1`、
`--jobs -5`、超长命令、emoji 输入、hook 的垃圾/超长/缺字段输入。

### 已修的两个真实缺陷（由该测试发现）

1. **argparse 参数错误返回 2，与"存在未验证"撞码** —— 下游会把"命令写错"误读成"有未验证项"。
   现统一为 3（自定义 `ArgParser`）。
2. **selfcheck 的"低一致"占用了 3** —— 与"用法错误"冲突。现低一致改为 4，3 专用于错误。
