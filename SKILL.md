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
    # Arrange
    cart = Cart(items=[Item(price=100)])
    coupons = []

    # Act
    result = cart.calculate_total(coupons)

    # Assert
    assert result == 100


def test_cart_total_with_conflicting_coupons_should_raise():
    """冲突的优惠券应抛出异常"""
    # Arrange
    cart = Cart(items=[Item(price=100)])
    coupons = [Coupon(type="满减", discount=10), Coupon(type="满减", discount=20)]

    # Act & Assert
    with pytest.raises(ValueError):
        cart.calculate_total(coupons)
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
