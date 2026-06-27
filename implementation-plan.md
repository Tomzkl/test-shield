# Test Shield Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建 Test Shield — 一个 Python 回归测试保护工具，`/test-shield` 命令触发，分析 git diff → 追踪调用链 → 分类影响 → 用户确认 → 生成 pytest 测试 → 运行验证。

**Architecture:** SKILL.md 作为 Claude Code 入口定义完整工作流，analyze.py 作为独立 AST 分析脚本提供可靠的调用链追踪（Claude 也可以通过 Grep 辅助分析），README.md 负责 GitHub 展示。

**Tech Stack:** Markdown (SKILL.md/README.md), Python 3.10+ stdlib ast module (analyze.py), pytest (测试生成目标)

## Global Constraints

- Python >= 3.10（使用 stdlib `ast` 模块，无外部依赖）
- SKILL.md 中的 `description` 字段必须是路由规则而非营销文案（决定 Claude 何时触发 Skill）
- 所有输出必须标注诚实边界：预估 vs 实测、追踪不到的情况
- v1 仅支持 Python + pytest
- 语言：中文优先，双语（README.md 中英双语）

---

### Task 1: 项目脚手架

**Files:**
- Create: `D:\test-shield\SKILL.md`（空文件）
- Create: `D:\test-shield\README.md`（空文件）
- Create: `D:\test-shield\scripts\analyze.py`（空文件）
- Create: `D:\test-shield\examples\demo.md`（空文件）

**Interfaces:**
- Produces: 三个空文件 + 一个空文件，后续 Task 填入内容

- [ ] **Step 1: 创建目录结构**

```bash
mkdir -p /d/test-shield/scripts /d/test-shield/examples
```

- [ ] **Step 2: 创建空文件**

```bash
touch /d/test-shield/SKILL.md
touch /d/test-shield/README.md
touch /d/test-shield/scripts/analyze.py
touch /d/test-shield/examples/demo.md
```

- [ ] **Step 3: 验证文件结构**

```bash
find /d/test-shield -type f
```

Expected output:
```
/d/test-shield/SKILL.md
/d/test-shield/README.md
/d/test-shield/scripts/analyze.py
/d/test-shield/examples/demo.md
/d/test-shield/test-shield-design.md
/d/test-shield/implementation-plan.md
```

- [ ] **Step 4: Commit**

```bash
cd /d/test-shield && git init && git add -A && git commit -m "chore: init test-shield project scaffold"
```

---

### Task 2: SKILL.md — Claude Code 入口

**Files:**
- Modify: `D:\test-shield\SKILL.md`

**Interfaces:**
- Produces: `/test-shield` 命令，Claude 按 SKILL.md 指令执行完整工作流

- [ ] **Step 1: 写入 SKILL.md**

```markdown
---
name: test-shield
description: 分析代码改动的影响范围，为意外波及的路径生成回归测试。当用户改了代码想确认没有引入回归 bug、想知道改动影响了哪些调用方、或者修完 bug 想补回归测试时使用。触发词：/test-shield、回归测试、我改了哪些地方会受影响、修完了帮我看有没有遗漏。
---

# Test Shield

你改了代码。我找到所有受影响的地方。为意外影响生成回归保护。

## 何时触发

用户显式调用 `/test-shield`，或说出以下意图：
- "我改了 X，帮我看看影响了哪些地方"
- "帮我生成回归测试"
- "修完了，确认一下有没有漏的"
- "这个改动安全吗"

## 核心原则

1. **AI 做追踪，人做判断。** 你不需要知道所有调用方——我帮你找。你只需要判断每个影响是预期还是意外。
2. **诚实。** 追踪不到就说追踪不到。预估就是预估。
3. **Deep over Wide。** v1 只支持 Python + pytest。
4. **Fails Loud。** 生成不了测试就说生成不了，不给假测试充数。

## 工作流

### 第 1 步：读取改动

运行以下命令获取改动：

```bash
git diff --name-only HEAD
git diff HEAD
```

如果工作区有未暂存改动，先用 `git diff`（未暂存），再用 `git diff --cached`（已暂存），合并分析。

如果没有改动 → 告知用户"没有检测到代码改动"，结束。

### 第 2 步：追踪受影响路径

对于每个改动的函数/方法，找到所有调用方：

**方法 A（优先）：** 运行 `python /d/test-shield/scripts/analyze.py <project_root>`
脚本会输出 JSON，包含：
- `changed_functions`: 改动的函数列表（文件 + 行号 + 函数名）
- `affected_callers`: 调用方列表（调用方文件 + 行号 + 函数名 + 被调函数）
- `dynamic_risks`: 检测到的动态调用风险（getattr/importlib/猴子补丁等）

**方法 B（降级）：** 如果脚本不可用，用 Grep 搜索：
```bash
grep -rn "function_name" --include="*.py" .
```

**如果 detect 到动态调用风险，必须在输出中标注：**
"⚠️ 检测到 importlib.import_module 在 auth.py:15，以下 2 条调用链可能不完整。"

### 第 3 步：分类展示

按以下格式展示受影响路径。**每次最多展示 5 条高风险路径。** 超过 5 条时，高风险展开、低风险折叠。

```
## 受影响路径分析

### ✅ 直接改动（你的改动目标）

| 文件 | 函数 | 行号 |
|------|------|------|
| discount.py | apply_coupon() | 38-52 |
| discount.py | validate_coupon() | 55-68 |

### ⚠️ 间接影响（下游调用方，你可能没意识到）

**高风险 — 核心逻辑被波及**
- **CartService.calculate_total()** — `cart.py:104`
  调用 `apply_coupon()` → 购物车总价计算受影响
  现有测试：❌ 无
  
- **RefundService.compute_refund()** — `refund.py:67`
  调用 `apply_coupon()` → 退款金额计算受影响
  现有测试：❌ 无

**低风险 — 工具/日志类调用（折叠）**
- Logger.log_discount() — `utils/logger.py:23`
- Metrics.record_coupon_usage() — `utils/metrics.py:15`
```

分类规则：
- **直接改动**：diff 中改动的函数本身
- **高风险间接影响**：调用改动函数的业务逻辑函数（非 utils/logging/metrics 等）
- **低风险间接影响**：工具函数、日志、监控、测试辅助

### 第 4 步：用户确认

对每条 ⚠️ 间接影响，询问用户：

```
对 CartService.calculate_total() — cart.py:104：
  A) 行为应保持不变 → 我生成回归测试，确保改动不破坏它
  B) 行为也要跟着变 → 我按新逻辑生成测试
  C) 不需要管 → 跳过
```

等待用户逐条回答。

### 第 5 步：生成测试

根据用户确认生成 pytest 格式测试。**每个测试必须满足：**

1. **有断言**：`assert result == expected`，不是 `print()`
2. **有业务含义的场景名**：
   - ✅ `test_cart_total_with_stacked_coupons_should_sum_discounts`
   - ❌ `test_case_1`
3. **覆盖边界**：正常值 + None/空值/边界值 + 异常路径
4. **独立可运行**：不依赖其他测试执行顺序
5. **标注覆盖行范围**：每个测试注释 `# AI预估覆盖: cart.py:100-115`

**测试文件命名规则：**
- 如果项目已有 `tests/` 目录 → 生成在 `tests/test_shield_regression_{module_name}.py`
- 如果没有测试目录 → 创建 `tests/` 目录并放入
- 如果已有同名文件 → 追加到文件末尾（用注释分隔 `# === Test Shield regression tests ===`）

**测试文件结构：**
```python
"""
Test Shield 自动生成的回归测试
生成时间: {timestamp}
改动范围: {changed_files}
预估覆盖: {estimated_coverage}
"""
import pytest
from {module} import {changed_functions}


# === 回归测试: CartService.calculate_total ===
# AI预估覆盖: cart.py:100-115


def test_cart_total_with_two_stackable_coupons_should_sum_discounts():
    """两个可叠加优惠券应正确累加"""
    # Arrange
    cart = Cart(items=[...])
    coupons = [Coupon(type="满100减10"), Coupon(type="满200减30")]
    
    # Act
    result = cart.calculate_total(coupons)
    
    # Assert
    assert result == expected_total


def test_cart_total_with_empty_coupons_should_return_original():
    """空优惠券列表应返回原价"""
    # ...


def test_cart_total_with_conflicting_coupons_should_raise():
    """冲突的优惠券应抛出异常"""
    # ...
```

### 第 6 步：运行测试

```bash
cd <project_root> && python -m pytest tests/test_shield_regression_*.py -v
```

如果 pytest 未安装 → 提示用户 `pip install pytest`，询问是否要安装。

**全部通过：**
```
✅ 回归测试通过 8/8

覆盖摘要：
- cart.py: calculate_total() → 3 个测试通过
- refund.py: compute_refund() → 3 个测试通过
- order.py: submit_order() → 2 个测试通过

你可以安全合入。这是证据。
```

**有失败：**
```
❌ 3/8 测试失败

失败列表（不自动修复，请你判断）：

1. test_cart_total_with_zero_inventory — AssertionError
   cart.py:133 — expected 0, got -1
   可能原因：库存为 0 时负数校验缺失

2. test_refund_with_partial_return — AssertionError
   refund.py:89 — expected 50, got 100
   可能原因：部分退款时全额计算了

3. test_submit_order_with_expired_coupon — pass (unexpected)
   这个测试通过了但看起来不该通过 — 请确认业务逻辑
```

**绝不自动修改测试。** 展示失败列表，让用户判断。

### 第 7 步：诚实报告

每个 `/test-shield` 结束时，在报告末尾附上：

```
## 诚实声明

| 项目 | 状态 |
|------|------|
| 调用链追踪方式 | AST 静态分析 / Grep 搜索 |
| 动态调用检测 | 已检测到 0 处 / 已检测到 N 处（标注在上方） |
| 测试覆盖行范围 | AI 预估（未运行覆盖率）/ 覆盖率验证已完成 |
| 可能遗漏 | 装饰器动态注入、猴子补丁、getattr/importlib |
```

## 特殊情况处理

### 项目中无 pytest
提示："未检测到 pytest。Test Shield 生成的测试需要 pytest 运行。要我帮你 `pip install pytest` 吗？"

### 改动涉及 50+ 调用方
"检测到 67 个调用方。这是一个大范围改动。建议分步进行。"
只展示高风险前 5 条，其余折叠为：
```
<details>
<summary>另外 62 个调用方（点击展开）</summary>
- Logger.log_discount() — utils/logger.py:23
- ...
</details>
```

### 追踪不到的情况
如果检测到以下模式，必须在分类展示中标注：
- `importlib.import_module()` — 动态导入
- `getattr(obj, method_name)` — 动态属性访问
- 装饰器动态注入的函数
- 猴子补丁

标注格式："⚠️ 检测到 getattr 在 core.py:42，以下调用链可能不完整。"

## 反模式 — 绝不做

- ❌ 不自动修测试
- ❌ 不自动 commit
- ❌ 不说"看起来没问题"（要说具体数字）
- ❌ 不生成没有断言的测试
- ❌ 不在用户没确认时生成测试
- ❌ 不假装能追踪动态调用
```

- [ ] **Step 2: 自检 SKILL.md**

检查清单：
- [x] frontmatter `name` 和 `description` 完整
- [x] `description` 是路由规则（包含触发词和场景描述）
- [x] 工作流 7 步完整覆盖设计文档的核心流程
- [x] 输出格式约束明确（5 条上限、3 行格式、诚实声明）
- [x] 测试质量门槛 5 条全部写入
- [x] 诚实边界 4 种情况全部覆盖
- [x] 特殊情况处理覆盖：无 pytest、50+ 调用方、追踪不到
- [x] 反模式/禁止事项列出

**一个关键验证：** 把 SKILL.md 的 `description` 字段单独拿出来看：

> 分析代码改动的影响范围，为意外波及的路径生成回归测试。当用户改了代码想确认没有引入回归 bug、想知道改动影响了哪些调用方、或者修完 bug 想补回归测试时使用。触发词：/test-shield、回归测试、我改了哪些地方会受影响、修完了帮我看有没有遗漏。

这既包含了功能描述（路由匹配用的关键词：回归测试、代码改动、影响、调用方），也包含了触发场景。合格。

- [ ] **Step 3: Commit**

```bash
cd /d/test-shield && git add SKILL.md && git commit -m "feat: add SKILL.md with complete workflow"
```

---

### Task 3: README.md — GitHub 首页

**Files:**
- Modify: `D:\test-shield\README.md`

**Interfaces:**
- Produces: GitHub 项目首页，面向开发者的完整介绍

- [ ] **Step 1: 写入 README.md**

```markdown
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
④ Wait for your judgment — keep behavior or update?
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
git clone https://github.com/YOUR_USERNAME/test-shield.git ~/.claude/skills/test-shield

# Or via Claude Code marketplace (coming soon)
# claude plugin marketplace add YOUR_USERNAME/test-shield
```

### Usage

```bash
cd your-python-project

# Make some changes...
# vim src/discount.py

# Run Test Shield
/test-shield
```

---

## Example

```bash
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
```

- [ ] **Step 2: 自检 README.md**

检查清单：
- [x] 一句话定位清晰
- [x] Problem/Solution 结构
- [x] 流程图展示核心价值
- [x] 竞品对比表突出差异化
- [x] 诚实说明做不到的事
- [x] 安装和使用说明
- [x] 中英双语（中文优先）
- [x] License 和 Contributing

- [ ] **Step 3: Commit**

```bash
cd /d/test-shield && git add README.md && git commit -m "docs: add README.md with full project introduction"
```

---

### Task 4: analyze.py — AST 调用链追踪脚本

**Files:**
- Create: `D:\test-shield\scripts\analyze.py`

**Interfaces:**
- Consumes: 项目根目录路径（命令行参数）
- Produces: JSON 输出到 stdout，包含 `changed_functions`, `affected_callers`, `dynamic_risks`

- [ ] **Step 1: 写入 analyze.py 的接口和参数解析**

```python
#!/usr/bin/env python3
"""
Test Shield — AST 调用链追踪脚本

分析 git diff 中的改动函数，通过 AST 静态分析找到所有调用方。
输出结构化 JSON 供 Claude Code 读取。

用法:
    python analyze.py <project_root>

输出 JSON 结构:
{
    "changed_functions": [
        {
            "file": "src/discount.py",
            "name": "apply_coupon",
            "line_start": 38,
            "line_end": 52,
            "class_name": null
        }
    ],
    "affected_callers": [
        {
            "caller_file": "src/cart.py",
            "caller_name": "calculate_total",
            "caller_line": 104,
            "callee_file": "src/discount.py",
            "callee_name": "apply_coupon",
            "risk": "high" | "low",
            "has_tests": false
        }
    ],
    "dynamic_risks": [
        {
            "file": "src/auth.py",
            "line": 15,
            "pattern": "importlib.import_module",
            "message": "动态导入可能隐藏调用链"
        }
    ],
    "stats": {
        "total_changed_functions": N,
        "total_affected_callers": N,
        "high_risk_count": N,
        "low_risk_count": N,
        "dynamic_risk_count": N
    }
}
"""

import ast
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


def run_git_diff(project_root: Path) -> str:
    """获取工作区所有改动（未暂存 + 已暂存）。"""
    result = ""
    try:
        unstaged = subprocess.run(
            ["git", "diff"],
            capture_output=True, text=True, cwd=project_root
        )
        if unstaged.stdout:
            result += unstaged.stdout
        staged = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True, text=True, cwd=project_root
        )
        if staged.stdout:
            if result:
                result += "\n"
            result += staged.stdout
    except Exception as e:
        print(json.dumps({"error": f"Git diff failed: {e}"}))
        sys.exit(1)
    return result
```

- [ ] **Step 2: 写入 diff 解析函数**

```python
def parse_diff_files(diff_text: str) -> List[Dict]:
    """从 git diff 输出中提取改动的文件和行号范围。

    Returns:
        [{"file": "src/discount.py", "added_lines": [(38, 52), (55, 68)]}]
    """
    if not diff_text.strip():
        return []

    changed_files = []
    current_file = None
    current_ranges = []

    for line in diff_text.split("\n"):
        # Match: diff --git a/src/foo.py b/src/foo.py
        if line.startswith("diff --git"):
            if current_file and current_ranges:
                changed_files.append({
                    "file": current_file,
                    "added_lines": merge_line_ranges(current_ranges)
                })
            match = re.match(r"diff --git a/(.+) b/(.+)", line)
            if match:
                current_file = match.group(2)
                current_ranges = []
        # Match: @@ -10,5 +10,8 @@
        elif line.startswith("@@") and current_file:
            match = re.match(r"@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@", line)
            if match:
                start = int(match.group(1))
                count = int(match.group(2)) if match.group(2) else 1
                current_ranges.append((start, start + count - 1))

    if current_file and current_ranges:
        changed_files.append({
            "file": current_file,
            "added_lines": merge_line_ranges(current_ranges)
        })

    return changed_files


def merge_line_ranges(ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
    """合并重叠的行号范围。"""
    if not ranges:
        return []
    sorted_ranges = sorted(ranges, key=lambda x: x[0])
    merged = [sorted_ranges[0]]
    for start, end in sorted_ranges[1:]:
        last_start, last_end = merged[-1]
        if start <= last_end + 1:
            merged[-1] = (last_start, max(last_end, end))
        else:
            merged.append((start, end))
    return merged
```

- [ ] **Step 3: 写入改动函数提取函数**

```python
def find_changed_functions(
    project_root: Path, changed_files: List[Dict]
) -> List[Dict]:
    """找到每个改动文件中受影响的函数。

    策略：解析 Python 文件的 AST，找出改动行范围内的函数定义。
    """
    results = []

    for file_info in changed_files:
        filepath = project_root / file_info["file"]
        if not filepath.exists() or not filepath.suffix == ".py":
            continue

        try:
            source = filepath.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue

        changed_ranges = file_info["added_lines"]

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_start = node.lineno
                func_end = node.end_lineno or func_start

                # 检查函数范围是否与改动行重叠
                for r_start, r_end in changed_ranges:
                    if func_start <= r_end and func_end >= r_start:
                        class_name = None
                        # 找到所属的类
                        for parent in ast.walk(tree):
                            if (isinstance(parent, ast.ClassDef)
                                    and parent.lineno <= func_start
                                    and (parent.end_lineno or parent.lineno) >= func_end):
                                if any(
                                    n is node
                                    for n in ast.walk(parent)
                                    if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
                                ):
                                    class_name = parent.name
                                    break

                        results.append({
                            "file": file_info["file"],
                            "name": node.name,
                            "line_start": func_start,
                            "line_end": func_end,
                            "class_name": class_name
                        })
                        break  # 此函数已匹配，跳过其余行范围

    return results
```

- [ ] **Step 4: 写入调用图构建函数**

```python
# 低风险路径模式 — 日志、工具、度量类函数
LOW_RISK_PATTERNS = [
    r"\.(debug|info|warning|error|critical|log)\(",
    r"\.(record|emit|send_metric|increment|gauge|histogram)\(",
    r"assertEqual|assertTrue|assertFalse|assertRaises|assertIn",
    r"unittest\.|pytest\.|self\.assert",
    r"@(staticmethod|classmethod|property|abstractmethod)",
    r"__repr__|__str__|__eq__|__hash__|__len__|__iter__",
    r"typing\.|Optional\[|Union\[|List\[|Dict\[|Set\[",
]


def is_low_risk(caller_name: str, caller_file: str) -> bool:
    """判断调用方是否为低风险（工具/日志/测试）。"""
    for pattern in LOW_RISK_PATTERNS:
        if re.search(pattern, caller_name):
            return True
    # 文件名指示
    low_risk_dirs = {"utils", "util", "helpers", "logging", "log", "metrics", "tests"}
    path_parts = Path(caller_file).parts
    if any(part in low_risk_dirs for part in path_parts):
        return True
    return False


def build_call_graph(
    project_root: Path, changed_functions: List[Dict]
) -> List[Dict]:
    """构建调用图：找到所有调用改动函数的代码位置。

    遍历项目中每个 Python 文件，解析 AST 找到函数调用，
    匹配调用目标与改动函数名。
    """
    affected = []
    # 构建改动函数的查找集合
    changed_set = {
        (f["file"], f["name"], f.get("class_name"))
        for f in changed_functions
    }

    for py_file in project_root.rglob("*.py"):
        file_str = str(py_file.relative_to(project_root)).replace("\\", "/")

        # 跳过虚拟环境、缓存、测试 Shield 自身
        skip_dirs = {".venv", "venv", "__pycache__", ".git", "node_modules",
                      "test-shield", ".pytest_cache"}
        if any(skip in py_file.parts for skip in skip_dirs):
            continue

        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue

        # 收集文件中定义的函数名（用于判断调用方函数名）
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            # 获取被调用的函数名
            callee_name = None
            if isinstance(node.func, ast.Name):
                callee_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                callee_name = node.func.attr

            if callee_name is None:
                continue

            # 检查是否匹配任一改动函数
            for changed in changed_functions:
                if callee_name != changed["name"]:
                    continue

                # 找到该调用所在的函数
                caller_func = find_enclosing_function(tree, node.lineno)
                caller_name = caller_func.name if caller_func else f"<module>:{file_str}:{node.lineno}"
                if isinstance(caller_name, str) and caller_name.startswith("<module>"):
                    caller_name_str = caller_name
                elif caller_func:
                    caller_name_str = caller_func.name
                else:
                    caller_name_str = f"<top-level>:{node.lineno}"

                # 判断风险等级
                risk = "low" if is_low_risk(caller_name_str, file_str) else "high"

                # 判断该调用方函数是否在改动文件本身中（那就是"直接改动"，不重复列出）
                caller_file_str = str(py_file.relative_to(project_root)).replace("\\", "/")

                # 检查是否有已有测试
                has_tests = check_has_tests(project_root, caller_file_str, caller_name_str)

                affected.append({
                    "caller_file": caller_file_str,
                    "caller_name": caller_name_str,
                    "caller_line": node.lineno,
                    "callee_file": changed["file"],
                    "callee_name": changed["name"],
                    "risk": risk,
                    "has_tests": has_tests
                })

    return affected


def find_enclosing_function(tree: ast.AST, lineno: int) -> Optional[ast.AST]:
    """找到包含指定行号的函数/方法节点。"""
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node_end = node.end_lineno or node.lineno
            if node.lineno <= lineno <= node_end:
                return node
    return None


def check_has_tests(
    project_root: Path, file_path: str, function_name: str
) -> bool:
    """检查项目中是否已有针对该函数的测试。"""
    # 简化检查：搜索 test 目录中是否出现函数名
    test_dirs = ["tests", "test", "testing"]
    for test_dir in test_dirs:
        test_path = project_root / test_dir
        if not test_path.exists():
            continue
        try:
            for py_file in test_path.rglob("test_*.py"):
                content = py_file.read_text(encoding="utf-8")
                if function_name in content:
                    return True
        except Exception:
            pass
    return False
```

- [ ] **Step 5: 写入动态调用风险检测**

```python
def detect_dynamic_risks(project_root: Path) -> List[Dict]:
    """检测项目中可能隐藏调用链的动态模式。"""
    risks = []
    patterns = {
        "importlib.import_module": "动态导入可能隐藏调用链",
        "getattr(": "动态属性访问可能隐藏调用",
        "__import__(": "动态导入可能隐藏调用链",
    }

    for py_file in project_root.rglob("*.py"):
        file_str = str(py_file.relative_to(project_root)).replace("\\", "/")

        skip_dirs = {".venv", "venv", "__pycache__", ".git", "node_modules",
                      "test-shield", ".pytest_cache"}
        if any(skip in py_file.parts for skip in skip_dirs):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue

        for pattern, message in patterns.items():
            if pattern in content:
                # 找到所有出现该模式的行号
                for i, line in enumerate(content.split("\n"), 1):
                    if pattern in line:
                        risks.append({
                            "file": file_str,
                            "line": i,
                            "pattern": pattern,
                            "message": f"{message} — {line.strip()[:80]}"
                        })

    return risks
```

- [ ] **Step 6: 写入 main 函数和入口**

```python
def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Usage: python analyze.py <project_root>",
            "changed_functions": [],
            "affected_callers": [],
            "dynamic_risks": [],
            "stats": {}
        }))
        sys.exit(1)

    project_root = Path(sys.argv[1]).resolve()
    if not project_root.is_dir():
        print(json.dumps({
            "error": f"Not a directory: {project_root}",
            "changed_functions": [],
            "affected_callers": [],
            "dynamic_risks": [],
            "stats": {}
        }))
        sys.exit(1)

    # 1. 获取 git diff
    diff_text = run_git_diff(project_root)

    # 2. 解析改动文件
    changed_files = parse_diff_files(diff_text)

    # 3. 找到改动的函数
    changed_functions = find_changed_functions(project_root, changed_files)

    # 4. 构建调用图
    affected_callers = build_call_graph(project_root, changed_functions)

    # 5. 检测动态风险
    dynamic_risks = detect_dynamic_risks(project_root)

    # 6. 去重 affected_callers（同一调用方可能因为多次调用而重复）
    seen = set()
    unique_callers = []
    for c in affected_callers:
        key = (c["caller_file"], c["caller_line"], c["callee_name"])
        if key not in seen:
            seen.add(key)
            unique_callers.append(c)

    # 7. 输出
    high_risk = [c for c in unique_callers if c["risk"] == "high"]
    low_risk = [c for c in unique_callers if c["risk"] == "low"]

    output = {
        "changed_functions": changed_functions,
        "affected_callers": unique_callers,
        "dynamic_risks": dynamic_risks,
        "stats": {
            "total_changed_files": len(changed_files),
            "total_changed_functions": len(changed_functions),
            "total_affected_callers": len(unique_callers),
            "high_risk_count": len(high_risk),
            "low_risk_count": len(low_risk),
            "dynamic_risk_count": len(dynamic_risks)
        }
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
```

- [ ] **Step 7: 验证 analyze.py 语法正确**

```bash
python -c "import ast; compile(open('/d/test-shield/scripts/analyze.py').read(), 'analyze.py', 'exec'); print('Syntax OK')"
```

Expected: `Syntax OK`

- [ ] **Step 8: Commit**

```bash
cd /d/test-shield && git add scripts/analyze.py && git commit -m "feat: add analyze.py — AST call chain tracing script"
```

---

### Task 5: demo.md — 演示场景

**Files:**
- Modify: `D:\test-shield\examples\demo.md`

**Interfaces:**
- Produces: 一个完整的使用演示，用于 README 链接和 Skill 自测

- [ ] **Step 1: 写入 demo.md**

```markdown
# Test Shield — 完整演示

## 场景

你维护一个电商项目。今天你要修改优惠券叠加逻辑。

### 改动前

```
src/
├── discount.py    # 优惠券逻辑
├── cart.py        # 购物车
├── refund.py      # 退款
└── order.py       # 下单
```

`discount.py:38-52` — `apply_coupon()` 函数，改动前允许两个优惠券叠加使用。

### 你的改动

你把 `apply_coupon()` 改了：同类型优惠券不可叠加，不同类型可叠加。

```python
# discount.py (改动后)
def apply_coupon(cart_total: float, coupons: list[Coupon]) -> float:
    """应用优惠券，同类型不可叠加"""
    applied_types = set()
    total_discount = 0.0
    for coupon in coupons:
        if coupon.type in applied_types:
            continue  # ← 你加了这个逻辑
        applied_types.add(coupon.type)
        total_discount += coupon.discount
    return max(0, cart_total - total_discount)
```

### 运行 /test-shield

```
$ /test-shield

## 受影响路径分析

✅ 直接改动
   discount.py — apply_coupon() — L38-52

⚠️ 间接影响

高风险 — CartService.calculate_total() — cart.py:104
  调用 apply_coupon() — 购物车总价受影响
  现有测试：❌ 无

高风险 — RefundService.compute_refund() — refund.py:67
  调用 apply_coupon() — 退款金额受影响
  现有测试：❌ 无

低风险 — Logger.record() — utils/logger.py:23
  调用 apply_coupon() — 日志记录（无业务影响）
```

### 用户确认

```
对 CartService.calculate_total()：A/B/C？
> A（行为应保持不变 — 购物车总价逻辑不应变）

对 RefundService.compute_refund()：A/B/C？
> A（行为应保持不变 — 退款逻辑不应变）
```

### 生成测试

Test Shield 为两个调用方各生成 3 个测试：

```python
# tests/test_shield_regression_discount.py

def test_cart_total_with_mixed_coupon_types_should_sum():
    """购物车：不同类型优惠券应正确累加"""
    cart = Cart(items=[Item(price=100)])
    coupons = [Coupon(type="满减", discount=10), Coupon(type="折扣", discount=20)]
    result = cart.calculate_total(coupons)
    assert result == 70  # 100 - 10 - 20

def test_cart_total_with_same_type_coupons_should_not_double_count():
    """购物车：同类型优惠券不重复计算"""
    ...

def test_cart_total_with_empty_coupons_should_return_original():
    """购物车：无优惠券返回原价"""
    ...

# ... refund 的 3 个测试类似
```

### 运行测试

```
$ pytest tests/test_shield_regression_discount.py -v

test_cart_total_with_mixed_coupon_types_should_sum ... PASSED
test_cart_total_with_same_type_coupons_should_not_double_count ... PASSED
test_cart_total_with_empty_coupons_should_return_original ... PASSED
test_refund_total_with_mixed_coupon_types ... PASSED
test_refund_total_with_same_type_coupons ... PASSED
test_refund_total_with_empty_coupons ... PASSED

✅ 6/6 通过

你可以安全合入。这是证据。
```

---

## 第二个场景：改动波及 50+ 调用方

改动 `UserService.get_user()` 核心函数 → 67 个调用方。

Test Shield 只展开高风险前 5 条，其余折叠：

```
⚠️ 高风险（展开，5 条）

- OrderService.assign_order() — order.py:45
- PaymentService.process_payment() — payment.py:23
- NotificationService.send_email() — notification.py:12
- ReportService.generate_monthly() — report.py:89
- AdminController.list_users() — admin.py:34

<details>
<summary>低风险（折叠，62 条）</summary>
- Logger.info() — utils/logger.py:15
- Metrics.increment() — utils/metrics.py:8
...
</details>
```

用户逐条确认高风险，低风险批量确认。
```

- [ ] **Step 2: Commit**

```bash
cd /d/test-shield && git add examples/demo.md && git commit -m "docs: add demo.md — full usage walkthrough"
```

---

### Task 6: 集成测试 — 用中国象棋项目验证

**Files:**
- 无需创建新文件

**Interfaces:**
- Consumes: SKILL.md, analyze.py, 中国象棋项目 backend/
- Produces: 验证 Skill 在实际项目中可用

- [ ] **Step 1: 在中国象棋项目中运行 analyze.py**

```bash
cd /d/chinese-chess-app/backend && python /d/test-shield/scripts/analyze.py .
```

Expected: 输出合法 JSON，包含 `changed_functions`、`affected_callers`、`dynamic_risks`、`stats`。

如果无 git diff（工作区干净），手动加一行注释触发改动：
```bash
echo "# test comment" >> app/main.py
python /d/test-shield/scripts/analyze.py .
git checkout app/main.py
```

- [ ] **Step 2: 验证 JSON 结构**

```bash
cd /d/chinese-chess-app/backend && python /d/test-shield/scripts/analyze.py . | python -c "
import json, sys
data = json.load(sys.stdin)
assert 'changed_functions' in data
assert 'affected_callers' in data
assert 'dynamic_risks' in data
assert 'stats' in data
assert 'total_changed_functions' in data['stats']
assert 'total_affected_callers' in data['stats']
print('JSON structure: OK')
for k, v in data['stats'].items():
    print(f'  {k}: {v}')
"
```

- [ ] **Step 3: Commit**

```bash
cd /d/test-shield && git add -A && git commit -m "test: integration validation against chinese-chess-app"
```

---

### Task 7: 最终自审

**Files:**
- 审阅所有已提交文件

- [ ] **Step 1: 对照设计文档检查完整性**

```bash
echo "=== 设计文档要求 vs 实现 ==="
echo "✅ SKILL.md 入口" && test -s /d/test-shield/SKILL.md && echo "  OK" || echo "  MISSING"
echo "✅ README.md 首页" && test -s /d/test-shield/README.md && echo "  OK" || echo "  MISSING"
echo "✅ analyze.py 脚本" && test -s /d/test-shield/scripts/analyze.py && echo "  OK" || echo "  MISSING"
echo "✅ demo.md 演示" && test -s /d/test-shield/examples/demo.md && echo "  OK" || echo "  MISSING"
echo "✅ 设计文档" && test -s /d/test-shield/test-shield-design.md && echo "  OK" || echo "  MISSING"
```

- [ ] **Step 2: 最终检查清单**

- [ ] SKILL.md `description` 是路由规则（非营销文案）
- [ ] SKILL.md 工作流 7 步完整
- [ ] SKILL.md 诚实边界覆盖全部 4 种动态调用
- [ ] SKILL.md 反模式/禁止事项列出
- [ ] README.md 一句话定位 + Problem/Solution + 竞品对比
- [ ] README.md 诚实说明做不到的事
- [ ] analyze.py 纯 stdlib，零外部依赖
- [ ] analyze.py 输出合法 JSON
- [ ] analyze.py 能处理空 diff、语法错误文件、大项目
- [ ] demo.md 完整演示流程
- [ ] 所有文件 UTF-8 编码

- [ ] **Step 3: 最终 commit**

```bash
cd /d/test-shield && git add -A && git status
```

---

## 完成标准

全部 7 个 Task 通过后，`D:\test-shield\` 目录包含：

```
test-shield/
├── .git/
├── SKILL.md           ✅ 完整工作流 + 路由描述 + 诚实边界
├── README.md          ✅ GitHub 首页 + 竞品对比 + 诚实说明
├── test-shield-design.md   ✅ 设计文档
├── implementation-plan.md  ✅ 本文件
├── scripts/
│   └── analyze.py     ✅ 零依赖 AST 分析 + JSON 输出
└── examples/
    └── demo.md         ✅ 完整使用演示
```
