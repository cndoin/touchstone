# 发版流程

> 版本号是**发布契约**的一部分。任何一处不一致，CI 会红，用户会困惑。
> 所以发版不是"打个 tag"，而是"把六处版本号改成同一个数，再打 tag"。

---

## 一、六处版本号（必须一致）

| # | 文件 | 位置 | 形态 |
|---|---|---|---|
| 1 | `VERSION` | 全文 | `3.4.2` |
| 2 | `SKILL.md` | YAML frontmatter | `version: 3.4.2` |
| 3 | `i18n/en/SKILL.md` | YAML frontmatter | `version: 3.4.2` |
| 4 | `CHANGELOG.md` | 顶部条目 | `## v3.4.2（2026-09-17）· ...` |
| 5 | `CITATION.cff` | `version` 字段 | `version: 3.4.2` |
| 6 | `CITATION.cff` | `preferred-citation.version` | `version: 3.4.2`（缩进一层，最容易漏） |

一键核对（`VER` 换成你要发的版本号）：

```bash
VER=3.4.2
grep -n "$VER" VERSION SKILL.md i18n/en/SKILL.md CHANGELOG.md CITATION.cff
# 六处都应有输出；少一处就说明漏改了
```

`scripts/stability_test.py` 的 E 组会自动校验 1/2/3/4，
`.github/validate-metadata.py` 会校验 1/5。

---

## 二、发版前检查清单

按顺序做完，每步都要**真的跑过**。

```bash
# 1. 三套测试全绿
python scripts/selftest.py          # 38/38
python scripts/robustness_test.py   # 70/70
python scripts/stability_test.py    # 99/99
python scripts/audit.py --strict    # ERROR=0 WARN=0

# 2. 元数据与资产校验
pip install pyyaml
python .github/validate-metadata.py

# 3. 同步安装目录（若本地装了 skill）
#    stability_test.py 的 G 组会比对工作区与安装目录，不一致会红
```

然后逐项确认：

- [ ] `CHANGELOG.md` 写了本次变更，且 **Keep a Changelog** 格式正确
- [ ] 新增的脚本已同步进 `README.md`「快速开始」与「目录结构」
- [ ] 新增的 hook 已同步进 `adapters/claude-code/README.md`
- [ ] 新增的论文引用已进 `CITATION.cff`，且**标题与作者列表照抄 arXiv 摘要页原文**
- [ ] 引用了新数字 → 已标注一手 / 二手，且**未超出原论文的限定域**（见下）
- [ ] `SECURITY.md` 的「支持版本」表已更新
- [ ] `README.en.md` 与 `README.md` 内容对齐（至少命令与用例数一致）

### 引用纪律（这条最容易出错）

文档里每个数字、每条论文结论，写进去之前必须确认三件事：

1. **出处真实存在** —— arXiv ID 逐个打开摘要页核对，不凭记忆
2. **限定域没被外推** —— 金融 QA 上测出的比例，不能写成"通用结论"
3. **一二手分明** —— 二手来源要写明"引用前需回溯原始出处"

> 已经有前科：arXiv 2607.11414 的 15–23% 是 FinQA 金融域、3 个 8–9B 模型的结果，
> 一度被 6 处文档写成通用定律。v3.4.2 已修（见 CHANGELOG）。别重蹈覆辙。

---

## 三、版本号怎么加

语义化版本 `MAJOR.MINOR.PATCH`：

| 变更 | 怎么动 |
|---|---|
| 修 bug、改文档、加测试用例 | `PATCH` |
| 新增核查能力、新增 hook、新增适配 | `MINOR` |
| 改退出码语义、改配置文件格式、删能力 | `MAJOR` |

**改了退出码语义必须 MAJOR** —— 下游 CI 依赖它做门禁，静默改语义等于打破别人的流水线。

---

## 四、打 tag

```bash
VER="$(cat VERSION)"          # 3.4.2
git tag -a "v$VER" -m "touchstone v$VER"
git push origin "v$VER"
```

`release.yml` 会：

1. 校验 tag == `v$(cat VERSION)`，不一致直接失败
2. 跑三套测试 + `audit.py --strict`
3. 用 `git archive` 打包（不含 `.git`）
4. 创建 GitHub Release 并附上 zip

---

## 五、发版后

- [ ] 确认 Release 页面有 zip 且能解包
- [ ] 确认 `python scripts/selftest.py` 在解包产物里能跑通
- [ ] 若改了安全相关行为，在 Release notes 里显式写出来
- [ ] 更新 `SECURITY.md` 的「支持版本」表（旧版本标记为 ❌）

---

## 出错了怎么办

| 情况 | 处理 |
|---|---|
| tag 打错了（还没推） | `git tag -d vX.Y.Z` 重打 |
| tag 推了但 CI 红 | 删 tag → 修 → **版本号 +1 后重打**（不要复用已发布版本号） |
| Release 已经发出但有缺陷 | 发新的 PATCH 版本，并在 Release notes 里说明；不要删已发布的 Release |
