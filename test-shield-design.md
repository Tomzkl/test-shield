# Test Shield — 设计文档

> 一句话：你改代码，我找到所有受影响的地方，为意外影响生成回归保护。

## 定位

| | 竞品（workersio/Vibe Test 等） | Test Shield |
|------|------|------|
| 做什么 | 全流程测试工作流 | **回归保护，只做回归保护** |
| 测什么 | 代码路径 | **被你改动波及的路径** |
| 透明度 | 内部分析，直接出测试 | **先展示受影响路径，等你判断** |
| 语言 | 通用 | **Python 先，做到极致** |
| 命令数 | 5-24 个 | **1 个：/test-shield** |
| 目标用户 | 有测试团队 | **一个人写代码的开发者** |

## 核心原则

1. **Deep over Wide** — v1 只支持 Python + pytest，做到 95 分再加下一门语言
2. **Evidence over Opinion** — 不说"看起来没问题"，说"已覆盖 8 条受影响路径，8/8 通过"
3. **Fails Loud** — 追踪不到就说追踪不到，不给假结果充数
4. **诚实** — 预估就是预估，不确定就说不知道

## 核心流程

```
/test-shield
     │
     ▼
① 读取 git diff → 精确知道你改了什么
     │
     ▼
② 追踪调用链 → 找到所有受影响路径
     │
     ▼
③ 分类展示（最多展示高风险路径，低风险折叠）：
     │
     ✅ 预期变化（你的改动应该有影响）
       └─ OrderService.apply_discounts()
     │
     ⚠️ 意外影响（你可能没意识到）
       └─ CartService.calculate_total()
       └─ RefundService.compute_refund()
     │
     对 ⚠️ 部分，每条问：
       A) 行为应保持不变 → 生成回归测试保护
       B) 行为也要跟着变 → 生成新逻辑的测试
     │
     ▼
④ 等你确认 → 生成测试
     │
     ▼
⑤ 跑测试 → 输出报告
     │
     ├─ 全部通过 → "你可以安全合入。这是证据。"
     └─ 有失败 → 标出来，交给你判断（不自动修测试）
```

## 输出格式（关键）

展示受影响路径时，每条不超过 3 行：

```
⚠️ 高风险 — discount.py:42 优惠叠加逻辑
   └─ 影响：OrderService / CartService / RefundService 共 3 个模块
   └─ 现有测试：0 个
   └─ 建议：为 3 个调用方各生成回归测试
```

**原因：** 超过 5 条高影响路径，用户就不读了。低风险路径折叠，用户点开才看。

## 测试质量门槛

每个生成的测试必须满足：

1. **有断言** — 不是 `print(x)`，是 `assert result == expected`
2. **有业务含义的场景名** — 不是 `test_case_1`，是 `test_calculate_total_with_two_stackable_coupons`
3. **覆盖边界** — 正常路径 + null/空值/边界值 + 异常路径
4. **独立可运行** — 不依赖其他测试的执行顺序
5. **标注覆盖行范围** — 每个测试注明"AI 预估覆盖 discount.py:38-52"，跑完覆盖率后用实际数据验证

## 诚实边界（必须写在输出里）

以下情况 Skill 追踪不到，必须告知用户：

- 动态加载（`getattr`、`importlib`、`__import__`）
- 反射调用（`hasattr` + 字符串调用）
- 装饰器动态注入的依赖
- 猴子补丁运行时替换的函数

**输出示例：** "⚠️ 检测到 importlib.import_module 在 auth.py:15，2 条调用链可能不完整。"

## 触发方式

手动：`/test-shield`（v1 不做自动触发，保持简单可控）

## v1 范围

**做：**
- Python 代码的 git diff 分析
- 基于 AST 的调用链追踪
- 预期/意外的分类展示
- pytest 格式的回归测试生成
- 测试自动运行 + 结果报告

**不做：**
- 自动修测试
- 自动 commit
- git 监听自动触发
- 非 Python 语言（Dart/TypeScript 留到 v2）
- CI/CD 集成（留到 v2）
- 50 条以上路径的复杂场景（留到 v2 优化）

## 文件结构（规划）

```
test-shield/
├── SKILL.md           # Skill 入口，Claude Code 读取
├── README.md          # GitHub 首页，面向用户
├── scripts/
│   └── analyze.py     # AST 调用链追踪脚本
└── examples/
    └── demo.md         # 使用演示
```
