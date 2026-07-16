# Test Shield 🛡️

> 你改代码。我找到所有受影响的地方。为意外影响生成回归保护。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-28%2F28%20passed-brightgreen)](https://github.com/dominicharmon-commits/test-shield/tree/master/tests)
[![Claude Code](https://img.shields.io/badge/Claude%20Code-skill-8A2BE2)](https://claude.com/claude-code)
[![Stars](https://img.shields.io/github/stars/dominicharmon-commits/test-shield?style=social)](https://github.com/dominicharmon-commits/test-shield)

A [Claude Code](https://claude.com/claude-code) skill that finds every call site affected by your code changes and generates targeted regression tests — **before** you break production.

> 📖 [Read the story behind it on dev.to](https://dev.to/dominic_harmon_18363706c7/i-built-a-claude-code-skill-that-finds-broken-callers-before-you-deploy-52a2)

<p align="center">
  <img src="examples/demo.gif" width="700" alt="Test Shield Demo">
</p>

> 🚀 **30 秒试用：** `bash examples/demo.sh` — 自动搭建演示项目、改代码、跑 Test Shield。不需要手动造任何东西。

---

## Which Way Do You Want to Use It?

| 我想... | 用这个 | 一句话 |
|---------|--------|--------|
| 🖥️ 在命令行快速查看改动影响了谁 | `python analyze.py . --summary` | 不需要 AI，不需要 Claude Code |
| 🚫 提交前自动检查高风险改动 | `python analyze.py --install-hook` | 以后每次 `git commit` 自动跑 |
| 🤖 让 AI 帮我生成回归测试 | `/test-shield` (Claude Code) | 交互式：追踪 → 确认 → 生成 pytest → 运行 |

---

## The Problem

You fix a bug in `discount.py`. You run your tests. All green. You deploy.

Three hours later: shopping cart totals are wrong. Refund amounts don't match. Orders are free.

**You changed one thing. It broke three others. Your tests didn't catch it.**

Existing test coverage tools tell you *which lines ran*. They don't tell you *which callers your change silently broke*.

---

## What Test Shield Does

```
/test-shield
     │
     ▼
① Reads your git diff — knows exactly what you changed
     │
     ▼
② Traces every caller — finds every downstream function affected
     │
     ▼
③ Shows you what it found — no black box
     ✅ Expected: the function you meant to change
     ⚠️ Unexpected: callers you didn't realize used it
     │
     ▼
④ Waits for your judgment — keep behavior or update?
     │
     ▼
⑤ Generates pytest regression tests — real assertions, real edge cases
     │
     ▼
⑥ Runs them — all green → ship. any red → stop and review.
```

---

## Quick Start

### Prerequisites

- Claude Code installed
- Python 3.10+
- A Python project tracked by git
- pytest (optional — Test Shield will offer to install it)

### Installation

```bash
# Clone to your Claude Code skills directory
git clone https://github.com/dominicharmon-commits/test-shield.git ~/.claude/skills/test-shield

# Or via Claude Code marketplace (coming soon)
# claude plugin marketplace add dominicharmon-commits/test-shield
```

### Try Without Claude Code (30 seconds)

```bash
# Clone and run the analyzer on any Python project
git clone https://github.com/dominicharmon-commits/test-shield.git
cd your-python-project
python ../test-shield/scripts/analyze.py .
```

You'll see exactly which functions your changes affect — no Claude Code required.

### Usage (with Claude Code)

```bash
cd your-python-project

# Make some changes...
# vim src/discount.py

# Run Test Shield
/test-shield
```

---

## Example

```
$ /test-shield

## 受影响路径分析

✅ 直接改动：discount.py — apply_coupon() (L38-52)

⚠️ 间接影响：

高风险 — CartService.calculate_total() — cart.py:104
  调用 apply_coupon() — 购物车总价受影响
  现有测试：❌ 无

高风险 — RefundService.compute_refund() — refund.py:67
  调用 apply_coupon() — 退款金额受影响
  现有测试：❌ 无

---
对 CartService.calculate_total()：行为应保持不变 or 也要改 or 跳过？
> A（保持不变）

对 RefundService.compute_refund()：行为应保持不变 or 也要改 or 跳过？
> A（保持不变）

---
生成 6 个回归测试...

✅ 6/6 通过

你可以安全合入。这是证据。
```

---

## Why Test Shield Over Alternatives

| | workersio/skills | Vibe Test | Test Shield |
|---|---|---|---|
| Test generation | ✅ | ✅ | ✅ |
| Call chain tracing | ❌ | ❌ | **✅ finds what you didn't know** |
| Expected vs unexpected | ❌ | ❌ | **✅ shows you what's surprising** |
| Human confirmation | ❌ | ❌ | **✅ you judge before tests written** |
| Single command | ❌ (5 commands) | ❌ (4 commands) | **✅ /test-shield** |
| Python depth | Generic | Generic | **✅ Python-first, deep** |
| Chinese support | ❌ | ❌ | **✅ 中文优先** |

---

## Known Limitations

**Test Shield is honest about what it can and can't do.** If something below is a dealbreaker, you'll know before you install it — not after.

### Tracing Blind Spots (Every Run Reports These)

| Pattern | Why Invisible | Example |
|---------|--------------|---------|
| `getattr(obj, "method")` | Method name not known until runtime | Plugin systems, dynamic dispatch |
| `importlib.import_module()` | Import target is a string variable | Feature flags, environment-based imports |
| Decorator injection | `@route()` may wrap functions in ways AST can't follow | Flask/FastAPI route decorators |
| Monkey-patching | Functions replaced at runtime by external code | Test mocks, hot-reload systems |
| `__import__()` | Same as importlib — dynamic import | Legacy code, meta-programming |

**What Test Shield does about it:** Every run ends with a "诚实声明" (honesty report) that flags detected dynamic patterns and explicitly marks uncertain call chains. No false confidence.

### Scope Limitations

- **Python only in v1.** TypeScript/Jest support on the roadmap (v1.2). If your stack is Node/Go/Rust, Test Shield won't help you yet.
- **pytest only.** unittest is partially supported (tests in `test_*.py` files are found), but generated tests use pytest syntax.
- **Static analysis only.** Test Shield does not execute your code. Dynamic call graphs (where the target depends on input data) cannot be traced.

### Design Choices (Not Bugs)

- **Doesn't auto-fix failing tests.** That's your call. Test Shield shows you what broke and suggests causes — you decide what to change.
- **Doesn't auto-commit.** You review the generated tests before they ship.
- **Generated tests are regression protection, not unit tests.** They verify "does this still behave the same way?", not "is this business logic correct?"

### Performance

| Project Size | analyze.py Runtime | Notes |
|-------------|-------------------|-------|
| < 50 .py files | < 1 second | Instant |
| 50-200 .py files | 1-3 seconds | Test cache kicks in |
| 200-1000 .py files | 3-10 seconds | Still acceptable |
| 1000+ .py files | 10-30 seconds | Consider running on changed modules only |

> v1.0 includes a test-caching optimization — test directories are scanned once and cached, not once per caller. `find_enclosing_function` is O(1) via pre-built line-to-function map. See `analyze.py` source for details.

---

## Roadmap

```
v1.0  ✅ Python + pytest · AST 追踪 · /test-shield · 测试缓存 · pre-commit · 增量分析
v1.5  🎯 VS Code 扩展 · GitHub PR Comment bot · Slack/飞书通知 · pre-commit hook
v2.0  🌍 多语言：TypeScript/Jest → Go → Rust
v2.5  📊 风险评分 (0-100) · 历史分析 · 行为 Diff
v3.0  🔗 跨仓库追踪 · 团队风险热力图 · 匿名风险模式数据库
```

| Version | What | Status |
|---------|------|--------|
| v1.0 | Python + pytest, AST tracing, /test-shield, test caching, `--pre-commit`, `--incremental` | ✅ Done |
| v1.5 | VS Code extension, GitHub PR comment bot, Slack/飞书/钉钉通知 | 🎯 Next |
| v2.0 | TypeScript/Jest → Go → Rust multi-language support | 🌍 Planned |
| v2.5 | Risk scoring (0-100), git history bug analysis, behavioral diff | 📊 Planned |
| v3.0 | Cross-repo tracing, team risk heatmap, anonymous risk pattern DB | 🔗 Vision |

---

## FAQ

Quick answers to common questions. More in **[docs/faq.md](docs/faq.md)**.

| Question | Answer |
|---------|--------|
| 为什么只支持 Python？ | v1 专注 Python 做到极致。TypeScript 在 v1.2。 |
| 和 pytest-cov 有什么区别？ | pytest-cov 告诉你哪些行没跑到。Test Shield 告诉你改了代码后哪些调用方会悄悄坏掉。互补关系。 |
| 能在 CI 里用吗？ | 暂时不行（v2.0 目标）。目前是本地手动触发 `/test-shield`。 |
| analyze.py 有依赖吗？ | 零依赖。纯 Python stdlib。Python 3.10+。 |
| 能追踪装饰器吗？ | 基础装饰器（`@staticmethod`等）可以。动态装饰器注入的函数追踪不到——会在诚实声明里标注。 |

---

## Contributing

Found a bug? Tracing missed a caller? **[Use the issue template →](https://github.com/dominicharmon-commits/test-shield/issues/new?template=bug-report.yml)**

Pull requests welcome. Before you start:
1. Run `pytest tests/ -v` — must be green
2. Keep `analyze.py` dependency-free (stdlib only)
3. One fix per PR

See **[CONTRIBUTING.md](CONTRIBUTING.md)** for details.

---

## 📢 Share

如果 Test Shield 帮你避免了一次线上事故——告诉另一个需要它的人。

**复制这段话发 Twitter/X / 知乎 / 朋友圈：**

> 改了一个函数，跑完测试全绿，上线三小时后炸了——因为没发现的调用方悄悄坏了。Test Shield 做一件事：找到你改动波及的所有调用方，为意外影响的那些生成回归测试。git diff → AST 追踪 → 你知道所有被影响的地方。GitHub 搜 "test-shield"。python analyze.py . 就能跑。

---

## License

MIT © 2026
