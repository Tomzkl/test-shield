# Changelog

本文件记录 Test Shield 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)。

---

## [1.0.0] - 2026-07-16

### 新增 (Added)

- `/test-shield` 命令：git diff → 调用链追踪 → 分类展示 → 用户确认 → 生成 pytest 测试 → 运行验证
- `scripts/analyze.py`：AST 调用链追踪脚本，零依赖，纯 Python stdlib
- 交互式确认流程：对每条受影响路径，用户选择 A) 保持行为 / B) 跟随变更 / C) 跳过
- 诚实声明：每次运行报告追踪方式、检测到的动态风险、已知盲点
- `--version` / `--help` CLI 标志
- 测试缓存优化：测试目录扫描一次，缓存复用（O(n*m) → O(n)）
- 行号→函数映射优化：预构建 map，O(1) 查表替代每次 O(n) 遍历
- 28 个单元测试 + 端到端测试，100% 通过
- import 别名追踪（`from x import y as z`）
- 动态调用风险检测（getattr、importlib、猴子补丁）
- 50+ 调用方自动折叠（高风险展开，低风险折叠）

### 文档 (Docs)

- README.md：项目入口、快速开始、示例、已知限制、FAQ 速查表
- SKILL.md：Claude Code 完整七步工作流
- CONTRIBUTING.md：贡献指南 + analyze.py 架构说明
- docs/faq.md：12 个高频问题
- examples/demo.md：三个完整场景演示
- examples/devto-article.md：项目故事和背景

### 限制 (Known Limitations — v1.0)

- Python + pytest 专属（TypeScript/Jest → v1.2）
- 无法追踪动态调用（getattr/importlib/猴子补丁/装饰器注入）
- 不自动修测试、不自动 commit
- 无 CI/CD 集成（→ v2.0）
- 静态分析仅限 AST 能解析的代码路径

---

## 版本规则

- **主版本号 (X.0.0)**：新语言支持、重大架构变更
- **次版本号 (0.X.0)**：新功能（覆盖率验证、CI 集成）
- **修订号 (0.0.X)**：bug 修复、性能优化、文档更新
