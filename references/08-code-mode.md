# 08 · 编码模式专项

> 编码场景的幻觉有专属形态：不是"事实说错"，而是**代码里出现了不存在的东西**，或者**声称跑通了其实没跑**。
> 公开基准：Collu-Bench（1.2k，代码幻觉）、ToolBeHonest（700，工具调用幻觉）

---

## 0. 先跑 dep_guard（v3 新增，编码场景第一条防线）

包幻觉是编码场景最危险的一类：模型编造包名 → 攻击者抢注同名包 → 一条 `npm install` 就是供应链攻击（slopsquatting）。

```bash
PY=python3          # Windows 用 python
"python3" scripts/dep_guard.py --root .           # 全项目
"python3" scripts/dep_guard.py --root . --offline # 只做本地判定
```

它抓的是编译器抓不到的东西：幻影路径、幻影依赖、registry 上不存在的包、新注册包（<90 天）、疑似 typosquat、命名导入的符号不存在。
详见 `14-supply-chain-code.md`。

---

## 1. 编码幻觉的四张面孔

| 面孔 | 例子 | 检测方式 |
|---|---|---|
| **幻影 import / 依赖** | `import com.squareup.moshi.kotlin.reflect.KotlinJsonAdapterFactory`（依赖里没有） | 编译 + 查 lockfile |
| **幻影 API** | 调用 `LazyColumn.flingBehavior { }`（该版本不存在） | 编译 + 查官方文档 |
| **错误的配置项 / 列名** | `androidx.room:room-runtime:2.7.1`（版本不存在）、`db.message_table` | registry 查询 / schema 检索 |
| **声称跑通** | "编译通过了"（其实没跑） | 贴完整构建输出 |

**共同点**：都能用机器 100% 判定。**这类问题不要靠 review，靠执刑——跑一遍。**

---

## 2. 编码场景的硬核查项（必跑）

```bash
PY=python3          # Windows 用 python

# 依赖坐标是否存在于 registry
python3 scripts/hardcheck.py --pypi requests 2.30.0
python3 scripts/hardcheck.py --npm react 18.3.1

# 文件/路径是否存在
python3 scripts/hardcheck.py --file app/src/main/java/.../Main.kt

# 命令是否真跑（贴真实输出）
python3 scripts/hardcheck.py --cmd "./gradlew :app:compileDebugKotlin"
```

### 项目专属核查（脚本外的部分）

| 项 | 怎么查 |
|---|---|
| Gradle/Maven 依赖版本 | 官方 registry（Maven Central / Gradle Plugin Portal）+ 本地 lockfile |
| AndroidX / Compose 版本号 | 官方 release notes；**不要凭记忆写 BOM 版本** |
| 第三方库 API 行为 | 查本地依赖源码（`~/.gradle/caches/...`）或官方文档 |
| 数据库列名 | 读实际 Entity 类 或 导出的 schema JSON |
| 配置项名 | grep 源码或官方文档，不在源码里的配置项一律不存在 |

---

## 3. 完成声明的证据要求

| 声称 | 必须给出的证据 |
|---|---|
| "编译通过" | 构建命令 + 完整输出（含 `BUILD SUCCESSFUL` / exit code 0） |
| "测试通过" | 测试命令 + pass/fail 计数，不是"应该过了" |
| "已创建文件 X" | `ls -la X` 输出 |
| "已修改 Y" | `git diff --stat` 或 diff 片段 |
| "Bug 已修复" | 复现步骤 → 修复前失败输出 / 修复后成功输出 |
| "服务已启动" | curl / 健康检查实际返回 |
| "已提交" | `git log -1` 输出（含 commit hash） |

**禁止**：用"应该""大概率""改动很小不可能出错"替代证据。

---

## 4. 与编译器的分工

编译器能抓的（类型错误、未定义符号）**不是幻觉治理的重点**——它会自己报错。

幻觉治理要抓的是编译器抓不到的：

| 编译器抓不到 | 例子 |
|---|---|
| 版本存在于 registry 但行为与记忆不符 | 用了 2.7 的 API 但项目锁在 2.6 |
| 配置项存在但含义理解错 | `android.enableJetifier=true` 被当成性能优化 |
| 逻辑正确但不符合项目约定 | 用了 Koin 而非账本里定的 Hilt |
| 测试通过但没覆盖真实场景 | 单测 mock 掉了出错路径 |
| 声称完成但未跑 | 最高频的一类 |

→ 编译器过了，还要过：**账本一致性 + 完成声明证据 + 回归集**。

---

## 5. 编码模式的工作流调整

```
[0] 判上下文：本仓库结构/内容 = Accurate（但必须实际读）
              第三方库行为 = Zero（查文档/源码，禁止凭记忆）
[1] 写代码前：查账本（约定/契约）+ 查 registry（版本）
[2] 写代码时：不确定的 API 立刻查，不写"应该能用"的代码
[3] 写完：    编译 + 测试实际跑，贴完整输出
[4] 声称完成：逐条 execution_claims 挂证据
[5] 闸门：    claim_lint.py 校验；大项目额外跑 ledger.py check --drift
```

---

## 6. 编码场景的特别禁令

1. **不写没验证过的依赖坐标。** `group:artifact:version` 三件套必须能解析。
2. **不写没验证过的 API 签名。** 参数名、类型、返回值结构来自文档或源码。
3. **不声称没跑过的命令结果。** 构建输出、测试计数、git log 一律实际执行。
4. **不把"编译通过"当成"功能正确"。** 编译只能证明语法与类型，不能证明行为。
5. **不改不属于本次任务范围的文件**，除非有明确依据；改动要用 `git diff` 自查。
