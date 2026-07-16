# Test Shield 🛡️

> **改一行代码 → 立刻知道影响了谁 → 提交前自动拦截高风险改动。**
>
> 零依赖。纯 Python stdlib。35 个测试全绿。

<p align="center">
  <img src="examples/demo.gif" width="700" alt="Test Shield Demo">
</p>

```bash
# 一行命令，立刻看到你的改动影响了哪些调用方
python analyze.py . --summary
```

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-35%2F35%20passed-brightgreen)](https://github.com/Tomzkl/test-shield)
[![Stars](https://img.shields.io/github/stars/Tomzkl/test-shield?style=social)](https://github.com/Tomzkl/test-shield)

---

## The Problem

你在 `discount.py` 里修了一个 bug。跑完测试。全绿。上线。

三小时后：购物车价格错了。退款金额对不上。有人免费下单。

**你改了一个函数。它悄悄坏了三个调用方。你的测试一个都没抓到。**

覆盖率工具告诉你哪些行跑到了。它们不告诉你**哪些调用方被你的改动悄悄破坏了**。

---

## What Test Shield Does

```
你改了 calculate_tax() — 加了一行 max(tax, 1.00)

Test Shield 在 0.5 秒内告诉你：

  [必须测] create_order()          — src/order.py:9    ← 订单创建被波及
  [必须测] process_refund()        — src/payment.py:39  ← 退款金额被波及
  [建议测] generate_monthly_report() — src/report.py:9  ← 月度报表被波及

  高风险且无测试: 3 个
  最小安全集: 补 2 个测试即可合入
  git commit → 被拦截
```

---

## Quick Start

```bash
# 1. 克隆
git clone https://github.com/Tomzkl/test-shield.git

# 2. 在你的 Python 项目里跑
cd your-python-project
python ../test-shield/scripts/analyze.py . --summary

# 3. 装上 pre-commit hook（一次）
python ../test-shield/scripts/analyze.py --install-hook
# 以后每次 git commit 自动检查。高风险无测试 → 拦截。
```

**前提：** Python 3.10+ · Git

---

## Commands

| 你想做什么 | 命令 |
|-----------|------|
| 看改动影响了谁 | `python analyze.py . --summary` |
| 提交前自动拦截 | `python analyze.py --install-hook`（一次） |
| 看函数历史上出过多少 bug | `python analyze.py . --history --summary` |
| 看整个项目哪些文件最危险 | `python analyze.py . --scan --summary` |
| 改共享库后查下游服务 | `python analyze.py . --repos ../svc-a,../svc-b` |
| 大型项目加速 | `python analyze.py . --incremental --summary` |

完整 CLI：`python analyze.py --help`

---

## Real Output

```
$ python analyze.py . --summary

  你改动了 src/services/payment.py:
    calculate_tax() L7-10

  间接影响 5 个调用方:
    [HIGH] create_order() - src/services/order.py:9  [无测试]
    [HIGH] process_refund() - src/services/payment.py:39  [无测试]
    [HIGH] generate_monthly_report() - src/services/report.py:9  [有测试]

  高风险且无测试: 2 个 <- 提交前建议生成回归测试

  --- 最小安全集 ---
  [必须测] 2 个 - 直接用户触达面
  补 2 个测试即可安全合入

  --- Git 考古 ---
     calculate_tax() - risk 12/100 (low)
     历史: 3 次修改, 0 次出过 bug

  --- 诚实声明 ---
  追踪方式: AST static analysis (full scan)
  动态风险: 0 处
  已知盲点: getattr/importlib/装饰器注入/猴子补丁
```

---

## Why This Over Alternatives

| | pytest-cov | SonarQube | Test Shield |
|---|-----------|-----------|-------------|
| 告诉你要测什么 | 行覆盖率 | 代码异味 | **你改的代码影响了哪些调用方** |
| 阻止坏提交 | ❌ | ❌ | **✅ pre-commit hook** |
| 调用链追踪 | ❌ | ❌ | **✅ AST 静态分析** |
| 零配置 | ✅ | ❌ | **✅** |
| 中文 | ❌ | ❌ | **✅** |

---

## Known Limitations

Test Shield 诚实告诉你它追踪不到的东西：

- `getattr(obj, "method")` — 动态属性访问
- `importlib.import_module()` — 动态导入
- 装饰器注入的函数
- 猴子补丁

**每次运行末尾都有诚实声明。** 追踪不到就说追踪不到，不假装。

---

## FAQ

| 问题 | 答案 |
|------|------|
| 为什么只支持 Python？ | v1 专注 Python 做到极致。TypeScript 在路线图上。 |
| 零依赖？ | `analyze.py` 纯 Python stdlib。不需要 pip install。 |
| 和 pytest-cov 有什么区别？ | pytest-cov 告诉你哪些行没跑到。Test Shield 告诉你改动波及了哪些调用方。互补。 |

更多：**[docs/faq.md](docs/faq.md)**

---

## Roadmap

```
v1.0  ✅ 全部完成（35 tests, 10 flags, 零依赖）
v2.0  🎯 TypeScript/Jest 支持
v2.5  📊 行为 Diff（实际运行新旧函数对比输出）
v3.0  🔗 CI/CD 集成 · GitHub PR Comment bot
```

---

## Contributing

Found a bug? Tracing missed a caller? → **[Open an Issue](https://github.com/Tomzkl/test-shield/issues)**

PRs welcome. `pytest tests/ -v` must be green. `analyze.py` stays stdlib-only.

---

## Star History

如果这个工具帮你避免了一次线上事故——**点个 Star 让更多人看到。**

---

MIT © 2026
