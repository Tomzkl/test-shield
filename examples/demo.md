# Test Shield — 完整演示

## 场景一：典型回归保护

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
"""Test Shield 自动生成的回归测试
改动范围: discount.py:38-52
"""

import pytest
from cart import Cart, CartItem
from discount import Coupon


# === 回归测试: CartService.calculate_total ===
# AI预估覆盖: cart.py:100-115

def test_cart_total_with_mixed_coupon_types_should_sum():
    """购物车：不同类型优惠券应正确累加"""
    cart = Cart(items=[CartItem(price=100)])
    coupons = [Coupon(type="满减", discount=10), Coupon(type="折扣", discount=20)]
    result = cart.calculate_total(coupons)
    assert result == 70  # 100 - 10 - 20


def test_cart_total_with_same_type_coupons_should_not_double_count():
    """购物车：同类型优惠券不重复计算"""
    cart = Cart(items=[CartItem(price=100)])
    coupons = [Coupon(type="满减", discount=10), Coupon(type="满减", discount=20)]
    with pytest.raises(ValueError):
        cart.calculate_total(coupons)


def test_cart_total_with_empty_coupons_should_return_original():
    """购物车：无优惠券返回原价"""
    cart = Cart(items=[CartItem(price=100)])
    result = cart.calculate_total([])
    assert result == 100


# === 回归测试: RefundService.compute_refund ===
# AI预估覆盖: refund.py:65-80

def test_refund_total_with_mixed_coupon_types():
    """退款：不同类型优惠券退款金额正确"""
    # ...


def test_refund_total_with_same_type_coupons():
    """退款：同类型优惠券按最后使用计算"""
    # ...


def test_refund_total_with_zero_discount():
    """退款：无优惠订单全额退款"""
    # ...
```

### 运行测试

```
$ pytest tests/test_shield_regression_discount.py -v

test_cart_total_with_mixed_coupon_types_should_sum ... PASSED
test_cart_total_with_same_type_coupons_should_not_double_count ... PASSED
test_cart_total_with_empty_coupons_should_return_original ... PASSED
test_refund_total_with_mixed_coupon_types ... PASSED
test_refund_total_with_same_type_coupons ... PASSED
test_refund_total_with_zero_discount ... PASSED

✅ 6/6 通过

你可以安全合入。这是证据。
```

---

## 场景二：改动波及 50+ 调用方

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
<summary>另外 62 个调用方（点击展开）</summary>
- Logger.info() — utils/logger.py:15
- Metrics.increment() — utils/metrics.py:8
...
</details>
```

用户逐条确认高风险，低风险批量确认。

---

## 场景三：测试跑不过 — 不自动修

```
$ /test-shield

... (生成 8 个测试，跑完后)

❌ 3/8 测试失败

失败列表（不自动修复，请你判断）：

1. test_cart_total_with_zero_inventory — AssertionError
   cart.py:133 — expected 0, got -1
   可能原因：库存为 0 时负数校验缺失

2. test_refund_with_partial_return — AssertionError
   refund.py:89 — expected 50, got 100
   可能原因：部分退款时全额计算了

3. test_submit_order_with_expired_coupon — PASS (unexpected)
   这个测试通过了但看起来不该通过 — 请确认业务逻辑
```

把失败原因展示清楚，交给用户判断。不自动修，不自动 commit。
