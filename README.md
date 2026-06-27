# Test Shield 🛡️

> 你改代码。我找到所有受影响的地方。为意外影响生成回归保护。

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

A [Claude Code](https://claude.com/claude-code) skill that finds every call site affected by your code changes and generates targeted regression tests — **before** you break production.

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

## What It Won't Do

- **Won't auto-fix failing tests** — that's your call
- **Won't auto-commit** — you review before you ship
- **Won't track dynamic calls** (getattr, importlib, monkey-patching) — it'll warn you when it can't
- **Won't support non-Python languages in v1** — Python first, done right
- **Won't pretend to be certain when it's not** — every test marks whether coverage range is AI-estimated or coverage-verified

---

## Roadmap

| Version | What |
|---------|------|
| v1.0 | Python + pytest, AST tracing, /test-shield command |
| v1.1 | Coverage verification (run pytest-cov after generation) |
| v1.2 | TypeScript / Jest support |
| v2.0 | CI/CD integration, git hook auto-trigger |

---

## Contributing

Found a bug? Tracing missed a caller? Open an issue with:
1. The Python code that wasn't traced correctly
2. Expected behavior: which caller should have been found
3. Actual behavior: what Test Shield reported

Pull requests welcome. Keep it focused — one fix per PR.

---

## License

MIT © 2026
