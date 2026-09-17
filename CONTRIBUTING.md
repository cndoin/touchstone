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
python3 scripts/selftest.py          # 快速冒烟（38 条，秒级）
python3 scripts/robustness_test.py   # 深度健壮性（70 条）
python3 scripts/stability_test.py    # 工程一致性（99 条，含文档/版本/安装同步）
python3 scripts/audit.py --strict    # 开源合规审计（WARN 也算失败）

# 元数据与资产校验（需要 PyYAML，仅本地/CI 用，不进产品代码）
pip install pyyaml
python3 .github/validate-metadata.py
```

五个都全绿再提 PR。**CI 会跑全部五个**（见 `.github/workflows/ci.yml`）：
三套测试在 py3.8 / 3.11 / 3.13 × Ubuntu / macOS / Windows 上跑，
`audit.py --strict` 与 `validate-metadata.py` 单独跑。

> `stability_test.py` 的 G 组会拿工作区和安装目录逐字节比对（2 条）。
> 跳过它时加 `--no-install-check`，此时是 **97 条** ——
> **不是 99 条少了两条测试，是 G 组整体跳过**。
> 安装目录不在默认位置时设 `TOUCHSTONE_INSTALLED=/path/to/skill`。
> CI 里没有安装目录，所以 CI 跑的就是 97 条。

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
文档写的版本号与 `VERSION` 是否一致、文档引用的文件是否真的存在、
工作区与安装目录是否同步。

**新增脚本 / 新增 hook 时，这三类测试各补一条：**
- `selftest.py`：正常路径 + 一条失败路径（断言退出码）
- `robustness_test.py`：垃圾输入不崩（绝不 Traceback）
- `stability_test.py`：一般不用改，A 组会自动把新 `.py` 纳入编译检查与 fuzz

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
