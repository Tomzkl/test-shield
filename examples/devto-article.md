# I Built a Claude Code Skill That Finds Broken Callers Before You Deploy

> You fix a bug. You deploy. Three hours later, production is on fire. Here's how I built a tool to stop that.

---

## The moment I realized I needed this

I was working on a Chinese chess app. Changed `is_checkmate()` — added a simple empty-board guard clause. Two lines. Trivial.

Ran my tests. Green. Deployed.

Two hours later: puzzle solving was broken. Level submission returned wrong results. **I changed one function. It silently broke two callers I didn't even know existed.**

The test coverage report said 87%. It didn't matter. Coverage tells you which lines ran — not which callers your change silently corrupted.

---

## What I built

**Test Shield** — a Claude Code skill with one job:

1. Read your git diff
2. Trace every caller of every changed function
3. Show you which impacts are expected (you meant to change that) and which are surprising (you didn't know that used it)
4. Generate pytest regression tests for the surprising ones
5. Run them — all green? Ship. Any red? Stop and fix.

```
/test-shield
     │
     ▼
Changed: is_checkmate() — chess_utils.py:320

⚠️  Unexpected impact:
  ● solve_puzzle() — levels.py:687     ← wouldn't have caught this
  ● submit_level_solution() — levels.py:516   ← or this

→ Generate 6 regression tests
→ 4/6 pass, 2 need review
→ Safe to merge. Here's the evidence.
```

---

## Why this is different from coverage tools

Coverage tells you: "Line 42 was executed during tests."

Test Shield tells you: "Line 42 changed. These 3 callers depend on it. They have zero tests. You didn't know about 2 of them."

One is about **what ran**. The other is about **what will break**.

---

## The hard lesson: what it won't do

I learned this the hard way during building: Python's dynamic nature means some callers are invisible to static analysis. `getattr()`, `importlib`, decorator injection, monkey-patching — AST tracing can't see through those.

So Test Shield doesn't pretend. Every run ends with a "honesty report":

```
Tracing method:         AST static analysis
Dynamic call risks:     0 detected
Known blind spots:      getattr, importlib, decorators
```

If it can't trace something, it tells you. No false confidence.

---

## Try it yourself

```bash
# Standalone — no Claude Code required
git clone https://github.com/dominicharmon-commits/test-shield.git
cd your-python-project
python ../test-shield/scripts/analyze.py .

# With Claude Code
/test-shield
```

Zero dependencies. Pure Python stdlib. Python 3.10+.

---

## What's next

- [ ] TypeScript/Jest support (v1.2)
- [ ] pytest-cov integration for coverage verification (v1.1)
- [ ] CI/CD integration (v2.0)

PRs welcome. MIT licensed.

---

*Built with Claude Code. Tested on a real production codebase. Stars appreciated.* ⭐
