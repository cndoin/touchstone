# 03 · M3 硬核查器（可判定项，先啃这些骨头）

> 来源：微软 RefChecker（arXiv 2607.00738）的"窄面核查"思路 + FacTool 的工具查询
> v2 新增：`scripts/hardcheck.py` 把这些检查变成可执行命令

**核心思想**：把核查目标收敛到**可判定的窄面**。开放式技术主张难以自动判定，但"这个 URL 存不存在""这个 DOI 对不对""这个文件在不在"是 100% 可判定的。

**先啃这些骨头**——成本极低（微软实测引用核查约 $0.04/篇量级），收益却是最高的一类错误：编造引用、编造 API、编造文件、编造命令输出。

---

## 1. 可判定项清单

| 类型 | 查法 | 可判定性 | 失败即 |
|---|---|---|---|
| **URL** | 实际发请求 / HEAD，看状态码 | 100% | 删除并留 `[]` |
| **DOI** | 解析到真实条目（doi.org content negotiation） | 100% | 删除 |
| **论文标题 + 作者** | 书目库比对；**作者列表严重不符**即判幻觉 | 高 | 删除或标 `unknown` |
| **实体**（公司/产品/工具/框架） | 检索 + 官方文档 | 高 | 标 `unknown` |
| **API 名称与参数** | Schema 校验 + 官方文档 | 100% | 删除，改用已确认存在的 API |
| **文件路径** | `ls` / `stat` 实际执行 | 100% | 不许声称存在 |
| **命令输出** | 实际执行并贴完整输出 | 100% | 不许编造输出 |
| **版本号** | 官方 changelog / package registry | 100% | 标 `unknown` |
| **法律条文 / 标准编号** | 官方数据库比对 | 高 | 删除 |
| **统计数据** | 回溯一手来源（论文/官方统计） | 中高 | 降格 `hearsay` 并点名来源 |
| **依赖坐标**（group:artifact:version） | registry 查询 / 本地 lockfile | 100% | 删除 |
| **配置项名 / 数据库列名** | 源码或 schema 实际检索 | 100% | 删除 |

---

## 2. 用脚本跑（v2）

```bash
PY=python3          # Windows 用 python

# 单个检查
python3 scripts/hardcheck.py --url https://example.com
python3 scripts/hardcheck.py --doi 10.1038/s41586-024-07500-0
python3 scripts/hardcheck.py --file ./src/Main.kt
python3 scripts/hardcheck.py --cmd "git status --porcelain"
python3 scripts/hardcheck.py --pypi requests 2.30.0
python3 scripts/hardcheck.py --npm react 18.3.1

# 批量（推荐）：把所有待查项写进 JSON 一次过
python3 scripts/hardcheck.py --batch checks.json --json-out result.json
```

`checks.json` 格式：

```json
{
  "urls": ["https://example.com"],
  "dois": ["10.1038/s41586-024-07500-0"],
  "files": ["./src/Main.kt", "./docs/arch.md"],
  "commands": ["git status --porcelain"],
  "pypi": [{"name": "requests", "version": "2.30.0"}],
  "npm": [{"name": "react", "version": "18.3.1"}]
}
```

**退出码语义（fail-closed）**：

| 退出码 | 含义 | 处理 |
|---|---|---|
| 0 | 全部通过 | 可声明 |
| 1 | 存在 `fail` | **相关声明必须删除或降级**，不许交付 |
| 2 | 存在 `unverified`（网络失败/超时） | 记为未验证，**不许默认通过** |
| 3 | 用法错误 | 修命令 |

**离线模式**：加 `--offline` 跳过所有网络项（URL/DOI/registry），只跑本地可判定项（文件/命令）。CI 或无网环境用这个。

**超时**：默认 8 秒，用 `--timeout 15` 调整。

---

## 3. 逐项人工核查模板（脚本覆盖不到的部分）

### URL / 链接

```
对每个要输出的 URL：
1. 实际发请求，记录状态码
2. 记录返回内容是否真的支持我要说的那句话
3. 404 / 超时 / 内容不符 → 删除
```

**绝不输出"我记得大概是这个地址"。**

### 论文 / 引用

```
1. 标题 + 作者 + 年份 三件套一起查
2. 作者列表严重不符 = 幻觉（即使标题相似）
3. 找不到 → 删，不要保留"疑似"的条目
```

> 微软实测：2025 年 NeurIPS 与 USENIX Security，**约每 20 篇就有 1 篇**含 ≥2 条疑似幻觉引用，获奖论文里也有。同行评审都拦不住，别指望自己"看着像真的"就放行。

### API / 库函数（编码场景高发）

```
1. 该 API 是否真的存在于当前使用的版本？
2. 参数名、类型、取值范围是否与官方文档一致？
3. 返回值结构是否如我所说？
→ 拿不准就查官方文档或本地依赖源码，不要靠训练记忆
```

幻影 API、幻影 import、错误的数据库列名、不存在的配置项——这是编码幻觉的主要形态。

### 文件 / 命令

```
"已创建 X 文件"  → ls -la 看一眼
"测试通过"       → 跑，贴完整输出（不是"应该过了"）
"已修改 Y"       → diff / git diff 看一眼
"服务已启动"     → curl 探一下
```

**自报状态不是证据。** 必须有可追溯的工具输出。

---

## 4. 执行原则

1. **查不到 = 不成立**，不是"大概成立"
2. **工具失败 ≠ 通过**。明确记为 `unverified`
3. **成本极低，不要省**。这类检查比任何推理都便宜
4. **批量做**：一次性把所有 URL / 实体 / 文件路径列出来，逐条过
5. **失败项要留痕**：删掉的条目写进 `unverified`，不要静默消失

---

## 5. 输出格式

```jsonc
"hard_checks": {
  "urls_resolved": "3/3",
  "dois_resolved": "1/2",        // 有 1 条被删除
  "entities_exist": "2/2",
  "apis_exist": "n/a",
  "files_exist": "1/1",
  "commands_executed": "2/2",
  "summary": {"total": 9, "pass": 8, "fail": 1, "unverified": 0},
  "removed": ["https://404.example.com"]   // 因核查失败被删除的条目
}
```
