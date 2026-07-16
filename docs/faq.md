# Test Shield — FAQ

---

## 为什么只支持 Python？

v1 的目标是**把一个语言做到 95 分，再加下一个**。Python 的 AST 模块（stdlib）让零依赖的静态分析成为可能——TypeScript 的 compiler API 可以做类似的事，但那是 v1.2 的活。

如果你需要 JS/TS 支持，在 Roadmap Issue 下 +1 或提 PR。

---

## 和 pytest-cov / coverage.py 有什么区别？

| | pytest-cov | Test Shield |
|---|-----------|-------------|
| 告诉你 | 哪些代码行没被测试跑到 | 你改的代码影响了哪些调用方 |
| 回答的问题 | "测试覆盖率够吗？" | "我这个改动安全吗？" |
| 触发时机 | 主动跑测试 | `git diff` 后手动触发 |

**它们是互补的。** 高覆盖率不意味着改动安全——一个改了内部逻辑的函数，调用方测试可能全绿但行为已经悄悄坏了。Test Shield 填补的是这个 gap。

---

## 能在 CI/CD 里用吗？

v1.0 不支持。目前 `/test-shield` 需要 Claude Code 的交互式确认（用户逐条判断预期/意外）。CI 里做自动回归测试 → Roadmap v2.0。

如果你现在就想要 CI 支持，可以单独跑 `analyze.py`：
```bash
python analyze.py . | jq '.affected_callers[] | select(.risk == "high" and .has_tests == false)'
```
这能帮你列出"高风险 + 没测试"的调用方，但不会自动生成测试。

---

## analyze.py 有外部依赖吗？

**零。** 纯 Python stdlib：`ast`、`json`、`re`、`subprocess`、`pathlib`。Python 3.10+。

这意味着你可以把它放进任何 Python 项目的 CI pipeline 里，不需要 `pip install` 任何东西。

---

## 能追踪装饰器和动态调用吗？

部分可以，部分不能。

- ✅ 基础装饰器（`@staticmethod`、`@classmethod`、`@property`）— AST 能正确解析
- ❌ 动态装饰器注入（如 Flask 的 `@app.route()` 动态注册的函数）— AST 追踪不到
- ❌ `getattr(obj, "method_name")` — 方法名是字符串变量，静态分析无能为力
- ❌ `importlib.import_module("dynamic.module")` — 同上
- ❌ 猴子补丁 — 运行时替换的函数，AST 看不到

**Test Shield 的做法：** 每次运行结束输出"诚实声明"，明确列出检测到的动态模式。不假装能追踪，不给假结果。

---

## 为什么生成的是 pytest 而不是 unittest？

pytest 更简洁（不需要类、不需要 `self.assertEqual`），生成和维护成本更低。同时 pytest 兼容运行 unittest 格式的测试，所以已有 unittest 测试不会受影响。

---

## 能用 analyze.py 而不装 Claude Code 吗？

可以。`analyze.py` 完全不依赖 Claude Code：

```bash
git clone https://github.com/dominicharmon-commits/test-shield.git
cd your-python-project
python ../test-shield/scripts/analyze.py .
```

Claude Code 只在需要 AI 来生成测试代码和交互式确认时才需要。纯分析步骤可以独立运行。

---

## 生成的测试文件在哪里？

在项目的 `tests/` 目录下，命名为 `test_shield_regression_{module_name}.py`。如果项目还没有 `tests/` 目录，会自动创建。

这些文件由人类审查后才合入。不要盲合。

---

## 为什么叫 Test Shield 而不是"回归测试生成器"？

Shield（盾牌）暗示**防护**而非修复。这个工具的工作是：你合入改动之前，帮你确认没有意外破坏任何东西。它不修 bug，它帮你预防 bug。

---

## 我怎么知道生成的测试是好测试？

每个生成的测试必须满足：
1. 有 `assert`（不是 `print()`）
2. 有业务含义的场景名（`test_cart_total_with_two_stackable_coupons` 而非 `test_case_1`）
3. 覆盖正常值 + 边界值 + 异常路径
4. 独立可运行（不依赖其他测试的执行顺序）

如果你觉得哪个测试不满足以上标准 → 提 Bug Report Issue，附上代码。

---

## 我的问题不在这里怎么办？

→ [提 Issue](https://github.com/dominicharmon-commits/test-shield/issues/new?template=bug-report.yml)，或者开 Discussion 讨论。
