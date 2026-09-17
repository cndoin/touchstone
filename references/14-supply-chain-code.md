# 14 · 供应链与编码幻觉：包幻觉 / slopsquatting

> 这是编码场景**最危险**的一类幻觉：不是"说错话"，是**写进代码里的假东西**，
> 而且会被攻击者利用变成供应链攻击。

---

## 1. 为什么单列一章

| 普通幻觉 | 包幻觉 |
|---|---|
| 写错一句话，人能看出来 | `npm install` 一行命令就把恶意包拉进构建 |
| 影响当次回答 | 影响整个项目、CI、生产环境 |
| 错了就错了 | **攻击者可以主动蹲守**：模型编造什么名字，他就注册什么名字 |

**slopsquatting**：模型编造一个"听起来合理"的包名 → 攻击者抢注同名包 → 下一个开发者（或 agent）执行安装命令 → 恶意代码进入构建。
与 typosquatting（打错字）不同：slopsquatting 的假名**往往与真名并不相似**，所以相似度启发式经常失效。

> 相关报道（**二手，引用前请回溯原始出处**）：
> - `huggingface-cli` 案例：AI 推荐的安装命令被原样写进公开仓库文档，该包三个月内被下载 3 万余次
> - `react-codeshift` 案例：通过 AI 生成的 agent skill 扩散到 237 个仓库
> - 有研究称 AI 生成代码的包幻觉率约 **19.7%**（USENIX 研究转述）
> - 分析称仅约 13% 的幻觉包名是"近似拼写"，约 49% 与任何真实包都高度不相似

**对 agent 尤其危险**：agent 会自己生成依赖、自己执行安装，全程不经过人眼。

---

## 2. 检查什么（可判定的窄面）

| 类型 | 判定方式 | 判定性 |
|---|---|---|
| **幻影路径** | 内部相对导入指向的文件是否存在（带扩展名补全） | 100% |
| **幻影依赖** | 该生态 manifest 中是否声明了这个包 | 100%（本地） |
| **包不存在** | registry（npm / PyPI）是否查得到 | 100%（联网） |
| **幻影符号** | 命名导入的符号是否真的被目标文件导出 | 高（本地文本匹配） |
| **新包特征** | 首版发布时间 < 90 天 | 100%（联网） |
| **typosquat 特征** | 与知名包名编辑距离 ≤ 阈值 | 中（启发式） |
| **无仓库链接** | registry 中 repository 字段为空 | 高（弱信号） |

---

## 3. 用 dep_guard.py

```bash
PY=python3          # Windows 用 python

"python3" scripts/dep_guard.py --root .                 # 全项目扫
"python3" scripts/dep_guard.py --root . --offline        # 只做本地判定（CI 无网时用）
"python3" scripts/dep_guard.py --root . --strict         # 可疑项也算失败
"python3" scripts/dep_guard.py --root . --files a.py b.ts
"python3" scripts/dep_guard.py --root . --allowlist allowed-pkgs.txt
```

**支持**：Python / JS·TS / Rust / Go / Kotlin·Java 的 import 提取；
npm / PyPI registry 核查；`package.json`、`requirements.txt`、`pyproject.toml`、`Pipfile`、`Cargo.toml`、`go.mod` 的声明比对。

**分级输出**：

| 级别 | 含义 | 处理 |
|---|---|---|
| `BLOCK` | 代码里有不存在的东西（幻影依赖 / 幻影路径 / registry 无此包） | **必须修** |
| `SUSPICIOUS` | 新包（<90 天）/ 疑似 typosquat | 安装前人工确认 |
| `WARN` | 弱信号（无仓库链接、命名导入符号未找到） | 看一眼 |
| `UNVERIFIED` | 网络不可用 / 该生态暂无自动核查 | **不是通过** |

---

## 4. 防误报的设计（重要）

自动检查一旦误报，人就会关掉它。所以刻意做了这些约束：

1. **跨生态不判**：npm 项目里的 Python 文件，不会拿 `package.json` 去判它的依赖
2. **标准库不判**：Python stdlib 与 Node 内置模块直接跳过
3. **默认导入不查符号**：`import bar from './x'` 的 `bar` 是本地绑定名，查不了；只查命名导入 `import { a, b } from './x'`
4. **gradle 不做未声明判定**：import 前缀与 `group:artifact` 不是一一对应，强行判会误报洪水
5. **网络失败记 UNVERIFIED**，不记 PASS

---

## 5. 流程上的防线（脚本之外）

| 层 | 做法 |
|---|---|
| 1. 允许清单 | 维护 `allowed-pkgs.txt`，新包需人工决策才能进 |
| 2. lockfile 纪律 | 提交 lockfile，CI 用 `npm ci` / 锁版本安装，不用裸 `npm install` |
| 3. 存在性 + 年龄核查 | 新增依赖前：registry 存在？首版时间？维护者？下载量？仓库链接？ |
| 4. 私有优先解析 | 内部包用 scope + 私有 registry，防"依赖混淆"组合技 |
| 5. agent 安装权限 | **不给 agent 无人值守的安装权**；依赖变更走 review |
| 6. 合并前闸门 | 任何 AI 新增的依赖，进 CI 过 `dep_guard.py`，人工复核残留项 |

> 上表第 2–6 条来自 2026 年多篇供应链安全实践文章的共识（**二手转述**），
> 但方向一致：lockfile + 存在性核查 + 人工闸门。

---

## 6. 与编译器的分工

编译器能抓"类型不存在"，抓不了"包被抢注了"。
`dep_guard.py` 抓的是编译器之前的东西：**这个依赖该不该存在、是不是真的、是不是新注册的**。

所以顺序是：`dep_guard.py` → 编译 → 测试 → `claim_lint.py` 交付闸门。
