# SPDX-License-Identifier: MIT

## 改了什么

<!-- 一句话。说不清就说明还没想清楚。 -->

## 为什么

<!-- 对应哪个 issue？复现过什么？ -->

## 验证过什么

> "应该没问题"不算验证。请贴**实际命令的实际输出**。

```bash
python scripts/selftest.py          # __/__ 通过
python scripts/robustness_test.py   # __/__ 通过
python scripts/stability_test.py    # __/__ 通过
python scripts/audit.py             # ERROR=__ WARN=__
```

补充验证（手工复现 / 边界输入 / 离线 / Windows 等）：

<!-- 没有的话写清楚为什么没有 -->

## 影响面

- [ ] 改了退出码语义 → 已在 `README.md` / `CONTRIBUTING.md` 同步
- [ ] 新增 / 删除脚本 → 已同步 `README.md`「快速开始」与「目录结构」
- [ ] 改了 hook → 已同步 `adapters/claude-code/README.md`
- [ ] 改了文档里的数字 / 论文引用 → 已标注一手 / 二手来源，且未改动原意
- [ ] 改了版本号 → `VERSION` / `SKILL.md` / `i18n/en/SKILL.md` / `CHANGELOG.md` / `CITATION.cff` 五处一致

## 硬约束自查

- [ ] 没有引入第三方依赖（只用 Python 标准库）
- [ ] 断网时退化为 UNVERIFIED，不崩溃
- [ ] hook 解析失败时**放行**，不阻断用户工作
- [ ] 新增脚本遵循退出码约定：0 通过 / 1 失败 / 2 未验证 / 3 用法错误

## 测试

- [ ] `selftest.py` 补了正常路径 + 一条失败路径
- [ ] `robustness_test.py` 补了垃圾输入不崩溃的用例
- [ ] 修 bug 的 PR 已把该 bug 做成回归用例
