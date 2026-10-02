# 贡献指南

欢迎 PR。但请注意：**这是一个反幻觉工具，它自己必须经得起怀疑。**
所以贡献的门槛不在代码风格，而在**可验证性**。

---

## 三条硬规则

1. **不许引入第三方依赖。** 所有脚本只能用 Python 标准库。
   理由：装上就能跑是这个套件的核心价值；有依赖就有版本冲突、有装不上的环境。
   审计脚本会自动拦截（`scripts/audit.py` 检查 import）。

2. **每条事实性声明必须可溯源。** 新增文档里的论文编号、百分比、榜单分数，
   必须标注**一手 / 二手**。二手数据要写明"引用前需回溯原始出处"。
   查不到就标 `unknown` —— 别让这个仓库自己产生幻觉。

3. **改脚本必须加测试。** 新功能要有用例，修 bug 要先把 bug 做成回归用例。

---

## 开发流程

```bash
python3 scripts/selftest.py          # 快速冒烟（118 条，秒级）
python3 scripts/robustness_test.py   # 深度健壮性（93 条）
python3 scripts/stability_test.py    # 工程一致性（104 条，含文档/版本/安装同步）
python3 scripts/audit.py --strict    # 开源合规审计（WARN 也算失败）

# 元数据与资产校验（需要 PyYAML，仅本地/CI 用，不进产品代码）
pip install pyyaml
python3 .github/validate-metadata.py
```

五个都全绿再提 PR。**CI 会跑全部五个**（见 `.github/workflows/ci.yml`）：
三套测试在 py3.8 / 3.11 / 3.13 × Ubuntu / macOS / Windows 上跑，
`audit.py --strict` 与 `validate-metadata.py` 单独跑。

> `stability_test.py` 的 G 组会拿工作区和安装目录逐字节比对（2 条）。
> 跳过它时加 `--no-install-check`，此时是 **102 条** ——
> **不是 104 条少了两条测试，是 G 组整体跳过**。
> 安装目录不在默认位置时设 `TOUCHSTONE_INSTALLED=/path/to/skill`。
> CI 里没有安装目录，所以 CI 跑的就是 102 条。

---

## 测试怎么写

**`selftest.py`**（快速冒烟）：
只放正常路径 + 关键失败路径。断言退出码。

```python
case("用例名", [脚本路径, "--参数"], 期望退出码)
```

**`robustness_test.py`**（深度）：
放边界、异常、编码、并发、性能、幂等。核心断言是
**不出现 Traceback + 退出码在 {0,1,2,3}**，而不是"结果是否正确"。

**`stability_test.py`**（工程一致性）：
放在前两套之外、但同样会让技能包"烂掉"的东西 ——
所有 `.py` 能否编译、重复执行是否一致、并发写会不会产出损坏 JSON、
垃圾输入下会不会崩、GBK/离线/只读目录/非 ASCII 路径下的行为、
文档写的版本号与 `VERSION` 是否一致、文档写的测试条数与实测是否一致、
文档引用的文件是否真的存在、
工作区与安装目录是否同步。

**新增脚本 / 新增 hook 时，这三类测试各补一条：**
- `selftest.py`：正常路径 + 一条失败路径（断言退出码）
- `robustness_test.py`：垃圾输入不崩（绝不 Traceback）
- `stability_test.py`：一般不用改，A 组会自动把新 `.py` 纳入编译检查与 fuzz

> **加了用例就要改文档里的条数。** `stability_test.py` 的 H 组拿一张登记表
> （`COUNT_RULES`）把「文档写的条数」和「实测条数」逐条比对，实测值来自当场
> 跑一遍 `selftest.py --json` / `robustness_test.py --json`。
> 所以**改完用例不用手工同步文档**——H 组会直接告诉你哪个文件写错了。
> 反过来，如果改了文档里条数的**写法**（比如把 `（N 条）` 改成 `共 N 项`，N 是任意数字），
> 要在 `COUNT_RULES` 里补一条，否则那句声明脱离保护；
> 而**登记了却匹配不到任何文本会判失败**，规则不会悄悄失效。

新增脚本时，请至少补：
- 正常输入 → 通过
- 空输入 / 损坏输入 → 用法错误（3）
- 网络不可用 → 未验证（2）而不是崩溃
- 不存在的路径 → 失败（1）

---

## 退出码约定（别破坏）

| 退出码 | 含义 |
|---|---|
| 0 | 通过 |
| 1 | 存在失败 |
| 2 | 存在未验证 |
| 3 | 用法/输入错误 |

`selfcheck.py` 例外：0=高一致，2=灰区，4=低一致，3=错误。

**新增脚本请沿用这套语义**，下游 CI 依赖它做门禁。

---

## 模块契约与边界（新增脚本前先读这一节）

体量变大之后，真正会烂掉的不是某个函数，而是**边界** ——
"这个能不能依赖那个"没有明文时，每个人（以及每个新会话的 AI）
都会各自发明一套。所以把已有的约定写死：

### 依赖方向

```
_common.py     ← 唯一的公共底座（退出码 / 输出 / 编码 / 原子写 / 缓存）
   ↑
scripts/*.py     只向下依赖 _common，**互不 import**
```

- **`scripts/` 下的脚本不许互相 import。** 当前是零横向耦合，请守住：
  一旦 A import B，B 的失败就会变成 A 的失败，单点问题扩散成链式问题。
  要共享逻辑就放进 `_common.py`。
- 脚本之间靠**子进程 + 退出码**协作（`pipeline.py` 就是这么串的）。
  这样任何一步崩溃都能被如实记成"该步 unverified"，而不是把整条链拖下水。

### 入口三件套（`scripts/` 下的产品脚本）

1. 开头调 `_force_utf8()` —— Windows 控制台默认 GBK，中文输出会炸
2. 用 `ArgParser`（来自 `_common`），**不要**直接用 `argparse.ArgumentParser`
   —— 参数错误的退出码必须是 **3**，不能是 argparse 默认的 2
3. 提供 `--json`；stdout 只出数据，人类提示一律走 stderr

**例外清单（这些例外是有理由的，不要"顺手统一"）：**

- `selftest.py` / `robustness_test.py` / `stability_test.py`：
  自建一份编码处理，**刻意不 import `_common`** ——
  测试脚本不该依赖被测代码，否则被测代码坏了，测试自己也起不来。
  三份实现的行为要保持一致（统一带 `errors="replace"`）。
- `adapters/claude-code/hooks/*.py`：会被拷进用户项目独立运行，可能根本没有
  `scripts/`，所以同样自带编码处理，也不走 CLI 参数（hook 从 stdin 收 JSON）。
- `.github/validate-metadata.py`：CI 专用，允许用 PyYAML，
  因此刻意放在 `.github/` 下，不参与 `scripts/` 的依赖审计，也没有 `main()`。
- `_common.py` 是库，没有 `__main__`。

### 哪个目录放什么

| 目录 | 放什么 | 约束 |
|---|---|---|
| `scripts/` | 产品脚本 + 三套测试 | 只用标准库；产品脚本遵守入口三件套 |
| `.github/` | CI 专用脚本 | 可用 PyYAML；不参与依赖审计 |
| `adapters/` | 各 harness 适配（hooks / 提示词） | **不许依赖 `scripts/`**，要能独立分发 |
| `references/` | 按需读的模式文档 | 不含可执行代码 |

### 什么该进 pipeline，什么不该

判据一句话：**能不能只看「当前产物 + 给定输入」就给出确定判定？**

- 能 → 进链（`hardcheck` / `dep_guard` / `claim_lint` / `bio_guard` / `tool_guard`）
- 不能 → 单独跑。分别是：需要时间维度（`regression`）、需要人
  （`ledger` / `model_profile`）、需要多轮采样（`selfcheck`）、
  对象是自己的运行时而不是交付物（三套测试）、
  或触发时机不同（`audit` 是发布前，`verifiers` 是灰区人工调用）

### 输出契约

- stdout **只出数据**（JSON 或结构化文本）；人类提示、错误、进度一律走 stderr
- `--json` 时 stdout 必须是**一个可解析的 JSON 对象**
- `_common.make_result(kind, target, status, ...)` 的 `kind` 是**检查器名**
  （`species` / `gene` / `citation` …），下游按它聚合。
  **不要塞文件路径** —— `bio_guard` 曾经就这么错过，聚合结果全失真、
  且没有任何测试发现，因为当时 JSON 只断言了"能解析"
- `--json` 的字段名一旦发布就是接口，改名按破坏性变更处理

### 每个脚本都要有测试引用

新增脚本时，三套测试里**至少有一处会真的跑它**。
零引用 = 没有回归保护 —— `audit.py` 就这样裸奔了很久
（280 行的发布前自检脚本，自己却不在任何检查范围内）。自查：

```bash
grep -c "你的脚本名.py" scripts/selftest.py scripts/robustness_test.py scripts/stability_test.py
```

### 性能上的硬边界

**单条正则不要出现"分组内量词 + 分组外量词"的嵌套结构**
（形如 `(X*)*`、`([^()]*(?:\([^()]*\)[^()]*)*)`）。
这类模式在"很长且匹配不上"的输入上会退化成 O(n²)：
`bio_guard` 的 `CALL_RE` 就被 20 万字符的单行拖到 120 秒超时。
`robustness_test.py` 的「超长单行」组专门盯这个，加新正则时留意。

---

## 加回归用例

真实出错一条，加一条到 `assets/regression-cases.json`：

```json
{
  "id": "case-006",
  "date": "2026-09-16",
  "source": "真实出错记录（脱敏）",
  "prompt": "当时的提问",
  "bad_output": "当时的错误输出",
  "error_type": "knowledge|tool|param|evidence|action|supply_chain",
  "why_wrong": "编造了什么",
  "expected_behavior": "正确行为是什么",
  "output": "本次待检输出（可留空 → 记为 SKIP）",
  "check": { "type": "must_contain|must_not_contain|must_abstain|must_have_source",
             "value": "..." }
}
```

注意：**提交前请脱敏**，不要带上真实项目路径、密钥、客户名。

---

## 文档语气

- 中文文档用简体中文，代码注释用中文
- 不写营销话术，不写"革命性""全球最强"这类无法验证的断言
- 每个数字都要有出处；没有出处的数字不许写进文档

---

## 许可与署名

本项目采用 **MIT**（见 `LICENSE`）。

**你提交 PR 即表示：**

1. 你有权提交这些内容，且这些内容不侵犯任何第三方的权利；
2. 你同意你的贡献**以 MIT 许可证授权给本项目及所有下游使用者** ——
   即 **inbound = outbound**：进来是什么许可，出去就是什么许可，不附加额外条件；
3. 你的贡献中若包含他人作品（代码片段、图表、文字），
   你已确认其许可证与 MIT 兼容，并在 `NOTICE` / `ATTRIBUTIONS.md` 中补上署名。

**只借鉴方法、不引入代码**是本仓库的一贯做法（见 `NOTICE`）。
如确需引入第三方源码，请先开 issue 说明理由 —— 大概率会被拒，
因为"零依赖 + 无第三方代码"是这个套件能被放心安装的前提。

学术引用请用 `CITATION.cff`（GitHub 仓库页侧边栏 "Cite this repository" 可直接导出
BibTeX / APA 等格式）。

---

## 提交信息

```
<类型>: <一句话说明>

类型：feat / fix / docs / test / refactor / chore
```

PR 描述里请说明：**你验证过什么**（跑了哪些命令、什么结果）。
"应该没问题"不算验证。
