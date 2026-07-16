#!/usr/bin/env python3
"""
Test Shield — AST 调用链追踪脚本

分析 git diff 中的改动函数，通过 AST 静态分析找到所有调用方。
输出结构化 JSON 供 Claude Code 读取。

用法:
    python analyze.py <project_root>
    python analyze.py --version
    python analyze.py --help

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
            "risk": "high",
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
        "total_changed_files": N,
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
import re
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

# 强制 UTF-8 输出，解决 Windows GBK 终端中文乱码
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

__version__ = "1.0.0"


def run_git_diff(project_root: Path) -> str:
    """获取工作区所有改动（未暂存 + 已暂存）。"""
    result = ""
    try:
        unstaged = subprocess.run(
            ["git", "diff"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=project_root
        )
        if unstaged.stdout:
            result += unstaged.stdout
        staged = subprocess.run(
            ["git", "diff", "--cached"],
            capture_output=True, text=True, encoding="utf-8",
            errors="replace", cwd=project_root
        )
        if staged.stdout:
            if result:
                result += "\n"
            result += staged.stdout
    except Exception as e:
        print(f"Error: git diff 失败 - {e}", file=sys.stderr)
        sys.exit(1)
    return result


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


def _build_class_map(tree: ast.AST) -> Dict[int, Optional[str]]:
    """构建行号 → 所属类名的映射。一次 AST 遍历，所有函数 O(1) 查表。"""
    class_map: Dict[int, Optional[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            node_end = node.end_lineno or node.lineno
            for lineno in range(node.lineno, node_end + 1):
                class_map[lineno] = node.name
    return class_map


def find_changed_functions(
    project_root: Path, changed_files: List[Dict]
) -> List[Dict]:
    """找到每个改动文件中受影响的函数。

    策略：解析 Python 文件的 AST，找出改动行范围内的函数定义。
    先构建 class 行号映射（O(n)），再检测函数（O(m)），总计 O(n+m)。
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
        class_map = _build_class_map(tree)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                func_start = node.lineno
                func_end = node.end_lineno or func_start

                for r_start, r_end in changed_ranges:
                    if func_start <= r_end and func_end >= r_start:
                        # O(1) 查 class 映射，替代原来的 O(n) full AST walk
                        class_name = class_map.get(func_start)

                        results.append({
                            "file": file_info["file"],
                            "name": node.name,
                            "line_start": func_start,
                            "line_end": func_end,
                            "class_name": class_name
                        })
                        break

    return results


# 低风险路径模式
LOW_RISK_PATTERNS = [
    re.compile(r"\.(debug|info|warning|error|critical|log|exception)\("),
    re.compile(r"\.(record|emit|send_metric|increment|gauge|histogram)\("),
    re.compile(r"assertEqual|assertTrue|assertFalse|assertRaises|assertIn"),
    re.compile(r"unittest\.|pytest\.|self\.assert"),
    re.compile(r"@(staticmethod|classmethod|property|abstractmethod)"),
    re.compile(r"__repr__|__str__|__eq__|__hash__|__len__|__iter__"),
    re.compile(r"typing\.|Optional\[|Union\[|List\[|Dict\[|Set\["),
]

LOW_RISK_DIRS = {"utils", "util", "helpers", "logging", "log", "metrics", "tests"}


def is_low_risk(caller_name: str, caller_file: str) -> bool:
    """判断调用方是否为低风险（工具/日志/测试类）。"""
    for pattern in LOW_RISK_PATTERNS:
        if pattern.search(caller_name):
            return True
    path_parts = Path(caller_file).parts
    if any(part in LOW_RISK_DIRS for part in path_parts):
        return True
    return False


SKIP_DIRS = {".venv", "venv", "__pycache__", ".git", "node_modules",
             "test-shield", ".pytest_cache", ".tox", "dist", "build",
             "site-packages", "egg-info"}


def find_enclosing_function(tree: ast.AST, lineno: int) -> Optional[ast.FunctionDef]:
    """找到包含指定行号的函数/方法节点。"""
    result = None
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node_end = node.end_lineno or node.lineno
            if node.lineno <= lineno <= node_end:
                if result is None or node.lineno >= result.lineno:
                    result = node
    return result


def build_test_cache(project_root: Path) -> Set[str]:
    """扫描项目测试目录，构建已测试函数名缓存。

    只扫描一次，所有 check_has_tests 调用共享此缓存。
    将 O(n*m) 降到 O(n) —— 对大型项目影响显著。
    """
    cache: Set[str] = set()
    test_dirs = ["tests", "test", "testing"]
    for test_dir in test_dirs:
        test_path = project_root / test_dir
        if not test_path.exists():
            continue
        try:
            for py_file in test_path.rglob("test_*.py"):
                try:
                    cache.add(py_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
            for py_file in test_path.rglob("*_test.py"):
                try:
                    cache.add(py_file.read_text(encoding="utf-8"))
                except Exception:
                    pass
        except Exception:
            pass
    return cache


def check_has_tests(test_cache_or_root, function_name: str) -> bool:
    """检查项目中是否已有针对该函数的测试。

    支持两种调用方式：
    - check_has_tests(Path, str) — 旧 API，每次扫描（向后兼容）
    - check_has_tests(Set[str], str) — 新 API，用预构建缓存 O(1) 查表
    """
    cache = test_cache_or_root
    if isinstance(cache, Path):
        # 向后兼容：收到 Path，临时构建缓存
        cache = build_test_cache(cache)
    if not cache:
        return False
    for content in cache:
        if function_name in content:
            return True
    return False


def build_line_to_function_map(tree: ast.AST) -> Dict[int, ast.FunctionDef]:
    """构建行号 → 包含该行的最内层函数的映射。

    一次 AST 遍历，之后所有 find_enclosing_function 调用都是 O(1) 字典查表。
    """
    mapping: Dict[int, ast.FunctionDef] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            node_end = node.end_lineno or node.lineno
            for lineno in range(node.lineno, node_end + 1):
                existing = mapping.get(lineno)
                if existing is None or node.lineno >= existing.lineno:
                    mapping[lineno] = node
    return mapping


def build_import_alias_map(tree: ast.AST) -> Dict[str, str]:
    """构建 import 别名映射表。

    解析 AST 中的 import 语句，将别名映射回原始函数名。
    例如: `from chess_utils import is_checkmate as check_mate`
    返回: {"check_mate": "is_checkmate"}
    """
    alias_map = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.asname:
                    alias_map[alias.asname] = alias.name
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.asname:
                    alias_map[alias.asname] = alias.name
    return alias_map


def build_call_graph(
    project_root: Path, changed_functions: List[Dict], incremental: bool = False
) -> List[Dict]:
    """构建调用图：找到所有调用改动函数的代码位置。

    如果 incremental=True，先用 grep 筛选可能受影响的文件，再 AST 解析——
    1000 文件的项目如果只改了 1 个函数，可能只解析 5-20 个文件而非全部。
    """
    affected = []
    test_cache = build_test_cache(project_root)

    # 增量模式：用 git grep 预筛选
    if incremental and changed_functions:
        py_files = _find_relevant_files(project_root, changed_functions)
    else:
        py_files = list(project_root.rglob("*.py"))

    for py_file in py_files:
        # 确保路径是 Path 对象
        if not isinstance(py_file, Path):
            py_file = Path(py_file)
        file_str = str(py_file.relative_to(project_root)).replace("\\", "/")

        if any(skip in py_file.parts for skip in SKIP_DIRS):
            continue

        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue

        # 构建当前文件的 import 别名映射和行号→函数映射
        alias_map = build_import_alias_map(tree)
        line_to_func = build_line_to_function_map(tree)

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            callee_name = None
            if isinstance(node.func, ast.Name):
                callee_name = node.func.id
            elif isinstance(node.func, ast.Attribute):
                callee_name = node.func.attr

            if callee_name is None:
                continue

            for changed in changed_functions:
                # 匹配：直接函数名 或 import 别名
                resolved_name = alias_map.get(callee_name, callee_name)
                if resolved_name != changed["name"]:
                    continue

                # O(1) 行号→函数查表
                caller_func = line_to_func.get(node.lineno)
                if caller_func:
                    caller_name_str = caller_func.name
                else:
                    caller_name_str = f"<module>:{node.lineno}"

                risk = "low" if is_low_risk(caller_name_str, file_str) else "high"

                # O(1) 缓存查表
                has_tests = check_has_tests(test_cache, caller_name_str)

                affected.append({
                    "caller_file": file_str,
                    "caller_name": caller_name_str,
                    "caller_line": node.lineno,
                    "callee_file": changed["file"],
                    "callee_name": changed["name"],
                    "risk": risk,
                    "has_tests": has_tests
                })

    return affected


def _find_relevant_files(project_root: Path, changed_functions: List[Dict]) -> List[Path]:
    """增量分析：找到引用改动函数的 Python 文件 + 改动文件本身。

    用 git grep 做快速文本搜索，只返回可能受影响的文件。
    对大型项目（1000+ .py 文件）可将 AST 解析量从全量降到 5-20 个文件。
    """
    candidate_paths: Set[Path] = set()

    # 始终包含改动文件本身
    for cf in changed_functions:
        fpath = project_root / cf["file"]
        if fpath.exists():
            candidate_paths.add(fpath)

    # 用 git grep 搜索每个改动函数名
    function_names = set(cf["name"] for cf in changed_functions)
    for fname in function_names:
        try:
            result = subprocess.run(
                ["git", "grep", "-l", "-F", fname, "--", "*.py"],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=project_root
            )
            if result.returncode == 0 and result.stdout.strip():
                for line in result.stdout.strip().split("\n"):
                    fpath = project_root / line.strip()
                    if fpath.exists():
                        candidate_paths.add(fpath)
        except Exception:
            pass

    return list(candidate_paths)


DYNAMIC_PATTERNS = {
    "importlib.import_module": "动态导入可能隐藏调用链",
    "getattr(": "动态属性访问可能隐藏调用",
    "__import__(": "动态导入可能隐藏调用链",
}


def detect_dynamic_risks(project_root: Path) -> List[Dict]:
    """检测项目中可能隐藏调用链的动态模式。"""
    risks = []

    for py_file in project_root.rglob("*.py"):
        file_str = str(py_file.relative_to(project_root)).replace("\\", "/")

        if any(skip in py_file.parts for skip in SKIP_DIRS):
            continue

        try:
            content = py_file.read_text(encoding="utf-8")
        except Exception:
            continue

        for pattern, message in DYNAMIC_PATTERNS.items():
            if pattern in content:
                for i, line in enumerate(content.split("\n"), 1):
                    if pattern in line:
                        risks.append({
                            "file": file_str,
                            "line": i,
                            "pattern": pattern,
                            "message": f"{message} - {line.strip()[:80]}"
                        })

    return risks


# === 三个预测功能 ===

# 风险 commit 关键词 — 匹配了说明这个函数历史上出过事
RISKY_COMMIT_PATTERNS = [
    re.compile(r"\bfix\b", re.IGNORECASE),
    re.compile(r"\bbug\b", re.IGNORECASE),
    re.compile(r"\bregression\b", re.IGNORECASE),
    re.compile(r"\brevert\b", re.IGNORECASE),
    re.compile(r"\bhotfix\b", re.IGNORECASE),
    re.compile(r"\bbreak(s|ing)?\b", re.IGNORECASE),
    re.compile(r"\bcrash\b", re.IGNORECASE),
    re.compile(r"\bwrong\b", re.IGNORECASE),
    re.compile(r"\bincorrect\b", re.IGNORECASE),
    re.compile(r"\bunexpected\b", re.IGNORECASE),
]

# 关键路径前缀 — 匹配了说明这个调用方是用户触达面
CRITICAL_PATH_PATTERNS = [
    re.compile(r"(api|endpoint|handler|controller|view|route)", re.IGNORECASE),
    re.compile(r"(create|delete|update|submit|process|checkout|pay|refund)", re.IGNORECASE),
]


def _analyze_git_history(project_root: Path, changed_functions: List[Dict]) -> List[Dict]:
    """Git 考古：分析每个改动函数的历史风险。

    用 git log 追踪函数所在文件的历史变更，
    统计总修改次数、风险 commit 次数、最近修改时间，
    输出 0-100 的风险评分。
    """
    history = []
    for cf in changed_functions:
        filepath = cf["file"]
        try:
            result = subprocess.run(
                ["git", "log", "--follow", "--oneline", "--", filepath],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=project_root
            )
            if result.returncode != 0 or not result.stdout.strip():
                history.append({
                    "function": cf["name"],
                    "file": filepath,
                    "total_commits": 0,
                    "risky_commits": 0,
                    "risk_score": 0,
                    "risk_level": "unknown",
                    "recent_risky": [],
                })
                continue

            commits = result.stdout.strip().split("\n")
            total = len(commits)
            risky = []
            for c in commits:
                for pat in RISKY_COMMIT_PATTERNS:
                    if pat.search(c):
                        risky.append(c.strip()[:80])
                        break

            risk_score = min(100, int((len(risky) / max(total, 1)) * 100 + len(risky) * 8))
            if risk_score >= 70:
                risk_level = "critical"
            elif risk_score >= 40:
                risk_level = "high"
            elif risk_score >= 15:
                risk_level = "medium"
            else:
                risk_level = "low"

            history.append({
                "function": cf["name"],
                "file": filepath,
                "total_commits": total,
                "risky_commits": len(risky),
                "risk_score": risk_score,
                "risk_level": risk_level,
                "recent_risky": risky[-3:],  # 最近 3 条风险 commit
            })
        except Exception:
            history.append({
                "function": cf["name"],
                "file": filepath,
                "total_commits": 0,
                "risky_commits": 0,
                "risk_score": 0,
                "risk_level": "error",
                "recent_risky": [],
            })

    return history


def _classify_criticality(
    callers: List[Dict], changed_functions: List[Dict]
) -> List[Dict]:
    """最小安全集分析：按"用户触达距离"分类每个调用方。

    [必须测] — 直接用户触达面（API/handler/controller/支付/退款）
    [建议测] — 间接用户触达（被关键路径调用、涉及资金计算）
    [可选]   — 内部工具/报表/日志
    """
    classified = []
    for c in callers:
        name = c["caller_name"]
        file = c["caller_file"]

        # 判断用户触达距离
        is_critical = False
        for pat in CRITICAL_PATH_PATTERNS:
            if pat.search(name) or pat.search(file):
                is_critical = True
                break

        if is_critical and c["risk"] == "high":
            tier = "must"       # 必须测
            tier_label = "[必须测]"
        elif c["risk"] == "high":
            tier = "should"     # 建议测
            tier_label = "[建议测]"
        else:
            tier = "optional"   # 可选
            tier_label = "[可选]  "

        classified.append({**c, "criticality": tier, "tier_label": tier_label})

    return classified


def _build_diff_command(cf: Dict, test_inputs: List[str]) -> str:
    """构建行为 Diff 的命令行建议（避免 f-string 中的反斜杠）。"""
    module_path = cf["file"].replace("/", ".").replace("\\", ".")
    if module_path.endswith(".py"):
        module_path = module_path[:-3]
    first_input = test_inputs[0] if test_inputs else ""
    return (
        "# 旧行为: git show HEAD:FILE | python -c '...'\n"
        f"# 新行为: python -c 'from {module_path} import {cf['name']};"
        f" print({cf['name']}({first_input}))'"
    )


def _behavioral_diff_suggestion(
    changed_functions: List[Dict], project_root: Path
) -> List[Dict]:
    """行为 Diff 建议：为每个改动函数生成一组输入/输出对比的测试框架。

    不做实际执行（安全考虑），而是生成测试输入建议和对比模板。
    用户可以用这个模板手动跑对比。
    """
    suggestions = []
    for cf in changed_functions:
        filepath = project_root / cf["file"]
        if not filepath.exists():
            continue

        try:
            source = filepath.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except Exception:
            continue

        for node in ast.walk(tree):
            if (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and node.name == cf["name"]):
                args = [a.arg for a in node.args.args if a.arg != "self"]
                # 根据参数名猜测测试输入
                test_inputs = _suggest_inputs(args, node.name)
                suggestions.append({
                    "function": cf["name"],
                    "file": cf["file"],
                    "args": args,
                    "suggested_inputs": test_inputs,
                    "comparison_cmd": _build_diff_command(cf, test_inputs),
                })
                break

    return suggestions


def _suggest_inputs(args: List[str], func_name: str) -> List[str]:
    """根据参数名启发式推测测试输入值。"""
    suggestions = []
    for arg in args:
        low = arg.lower()
        if any(w in low for w in ("amount", "price", "total", "tax", "rate", "discount")):
            suggestions.append("0, 1, 100, 1000")
        elif any(w in low for w in ("name", "id", "code", "key", "token", "email")):
            suggestions.append('"test_value", "", None')
        elif any(w in low for w in ("items", "orders", "data", "list", "array")):
            suggestions.append("[], [{}]")
        elif any(w in low for w in ("flag", "enable", "debug", "verbose")):
            suggestions.append("True, False")
        elif any(w in low for w in ("count", "limit", "offset", "page", "size")):
            suggestions.append("0, 1, 10, 100")
        else:
            suggestions.append("0, None, 'test'")
    return suggestions


# === v3.0: 跨仓库 · 热力图 · 匿名模式 ===


def _scan_project(project_root: Path) -> List[Dict]:
    """项目风险热力图：扫描整个项目的所有 .py 文件，按风险从高到低排名。

    每个文件分析：
    - git 历史（修改次数、bug 频率）
    - 调用方密度（项目中多少地方调用这个文件的函数）
    - 综合风险评分 0-100
    """
    file_risks = []
    all_functions = []
    file_to_functions: Dict[str, List[str]] = {}

    # 第一步：收集所有函数
    for py_file in project_root.rglob("*.py"):
        file_str = str(py_file.relative_to(project_root)).replace("\\", "/")
        if any(skip in py_file.parts for skip in SKIP_DIRS):
            continue
        try:
            tree = ast.parse(py_file.read_text(encoding="utf-8"))
        except Exception:
            continue

        funcs_in_file = []
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                funcs_in_file.append(node.name)
                all_functions.append({
                    "name": node.name,
                    "file": file_str,
                    "line": node.lineno,
                })
        if funcs_in_file:
            file_to_functions[file_str] = funcs_in_file

    # 第二步：计算每个文件的调用方密度
    func_to_callers: Dict[str, int] = {}
    for func_info in all_functions:
        count = 0
        for py_file in project_root.rglob("*.py"):
            if any(skip in py_file.parts for skip in SKIP_DIRS):
                continue
            try:
                content = py_file.read_text(encoding="utf-8")
                if func_info["name"] in content:
                    count += 1
            except Exception:
                pass
        func_to_callers[func_info["name"]] = max(0, count - 1)  # -1 = 排除自身

    # 第三步：Git 历史风险
    for file_str, funcs in file_to_functions.items():
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "--", file_str],
                capture_output=True, text=True, encoding="utf-8",
                errors="replace", cwd=project_root
            )
            total = 0
            risky = 0
            if result.returncode == 0 and result.stdout.strip():
                commits = result.stdout.strip().split("\n")
                total = len(commits)
                for c in commits:
                    for pat in RISKY_COMMIT_PATTERNS:
                        if pat.search(c):
                            risky += 1
                            break

            # 调用方密度评分
            caller_density = sum(func_to_callers.get(f, 0) for f in funcs)
            density_score = min(50, caller_density * 3)

            # 历史风险评分
            history_score = min(50, int((risky / max(total, 1)) * 100 + risky * 5))

            risk_score = density_score + history_score
            if risk_score >= 70:
                level = "critical"
            elif risk_score >= 40:
                level = "high"
            elif risk_score >= 20:
                level = "medium"
            else:
                level = "low"

            file_risks.append({
                "file": file_str,
                "functions": len(funcs),
                "caller_density": caller_density,
                "total_commits": total,
                "risky_commits": risky,
                "density_score": density_score,
                "history_score": history_score,
                "risk_score": risk_score,
                "risk_level": level,
            })
        except Exception:
            file_risks.append({
                "file": file_str,
                "functions": len(funcs),
                "risk_score": 0,
                "risk_level": "error",
            })

    # 第四步：按风险从高到低排序
    file_risks.sort(key=lambda x: x["risk_score"], reverse=True)
    return file_risks


def _cross_repo_search(
    project_root: Path, changed_functions: List[Dict], repo_paths: List[str]
) -> List[Dict]:
    """跨仓库追踪：在关联仓库中搜索改动函数的调用方。

    repo_paths: 逗号分隔的仓库路径列表。
    """
    cross_callers = []
    for repo_path_str in repo_paths:
        repo_path = Path(repo_path_str.strip()).resolve()
        if not repo_path.is_dir() or not (repo_path / ".git").is_dir():
            continue

        for py_file in repo_path.rglob("*.py"):
            file_str = str(py_file.relative_to(repo_path)).replace("\\", "/")
            if any(skip in py_file.parts for skip in SKIP_DIRS):
                continue

            try:
                content = py_file.read_text(encoding="utf-8")
            except Exception:
                continue

            for cf in changed_functions:
                if cf["name"] in content:
                    cross_callers.append({
                        "caller_repo": str(repo_path),
                        "caller_file": file_str,
                        "callee_name": cf["name"],
                        "callee_repo": str(project_root),
                        "callee_file": cf["file"],
                    })

    return cross_callers


def _export_anonymized_risk(output: dict) -> dict:
    """导出匿名风险数据：剥离文件和函数名，仅保留模式特征。

    安全：输出不含路径/函数名/仓库信息，可以公开分享。
    """
    anonymized = {
        "version": __version__,
        "export_time": None,  # 由调用者填充
        "patterns": {
            "total_changed_functions": output["stats"]["total_changed_functions"],
            "total_affected_callers": output["stats"]["total_affected_callers"],
            "high_risk_untested_ratio": (
                round(output["stats"]["high_risk_untested_count"] /
                      max(output["stats"]["total_affected_callers"], 1), 2)
            ),
            "minimal_safe_set_ratio": (
                round(output["stats"]["minimal_safe_set"]["must_test"] /
                      max(output["stats"]["high_risk_untested_count"], 1), 2)
            ),
        },
        "caller_risk_distribution": {
            "high_risk": output["stats"]["high_risk_count"],
            "low_risk": output["stats"]["low_risk_count"],
        },
        "tracing_method": output["honesty_report"]["tracing_method"],
        "dynamic_risks_detected": output["honesty_report"]["dynamic_risks_detected"],
    }

    if output.get("git_archaeology"):
        scores = [g["risk_score"] for g in output["git_archaeology"]]
        anonymized["patterns"]["avg_git_risk_score"] = (
            round(sum(scores) / len(scores), 1) if scores else 0
        )
        anonymized["patterns"]["max_git_risk_score"] = max(scores) if scores else 0
        anonymized["patterns"]["functions_with_bug_history"] = sum(
            1 for g in output["git_archaeology"] if g["risky_commits"] > 0
        )

    return anonymized


def _print_heatmap(output: dict) -> None:
    """打印项目风险热力图（人类可读）。"""
    heatmap = output["heatmap"]
    summary = output["summary"]

    print(f"\n  项目风险热力图 — {output['project']}")
    print(f"  扫描文件: {output['total_files_scanned']} 个 .py 文件")
    print(f"  Critical: {summary['critical']} | High: {summary['high']} | "
          f"Medium: {summary['medium']} | Low: {summary['low']}")
    print(f"\n  {'排名':<5} {'风险':<8} {'文件':<50} {'函数':<6} {'历史'}")
    print(f"  {'-'*4}  {'-'*7}  {'-'*49}  {'-'*5}  {'-'*10}")

    for i, h in enumerate(heatmap[:20], 1):
        icon = {70: "!!", 40: "! ", 20: "~ ", 0: "  "}.get(
            max(k for k in [70, 40, 20, 0] if h["risk_score"] >= k), "  ")
        hist = f"{h.get('total_commits', 0)}改/{h.get('risky_commits', 0)}bug" if h.get("total_commits") else "N/A"
        print(
            f"  {i:<4} {icon} {h['risk_score']:<4}  "
            f"{h['file']:<49} {h['functions']:<5} {hist}"
        )

    if len(heatmap) > 20:
        print(f"  ... 另外 {len(heatmap) - 20} 个文件（用 --help 查看完整输出）")

    # Top 3 建议
    if heatmap:
        top = [h for h in heatmap if h["risk_level"] in ("critical", "high")][:3]
        if top:
            print(f"\n  --- 优先加固 Top 3 ---")
            for i, h in enumerate(top[:3], 1):
                print(f"  {i}. {h['file']} — 为 {h['functions']} 个函数补充回归测试")
    print()


def _export_anonymized_risk_for_scan(output: dict) -> dict:
    """为 --scan 模式导出的匿名风险数据（不包含文件名）。"""
    heatmap = output.get("heatmap", [])
    if not heatmap:
        return {"mode": "scan", "error": "no data"}
    scores = [h.get("risk_score", 0) for h in heatmap]
    return {
        "mode": "scan",
        "version": __version__,
        "total_files": len(heatmap),
        "risk_distribution": output.get("summary", {}),
        "avg_risk_score": round(sum(scores) / len(scores), 1),
        "max_risk_score": max(scores),
        "top_pattern": (
            "high caller density + frequent buggy commits"
            if any(h.get("risky_commits", 0) > 2 for h in heatmap[:5])
            else "moderate risk - no concentrated danger zones"
        ),
    }


def main():
    if len(sys.argv) < 2:
        _print_usage()
        sys.exit(1)

    if sys.argv[1] in ("--version", "-V", "-v"):
        print(f"test-shield v{__version__}")
        sys.exit(0)

    if sys.argv[1] in ("--help", "-h"):
        _print_help()
        sys.exit(0)

    # --install-hook：一键安装 pre-commit hook
    if sys.argv[1] == "--install-hook":
        _install_pre_commit_hook()
        return

    # 解析参数
    args = sys.argv[1:]
    pre_commit_mode = "--pre-commit" in args
    incremental_mode = "--incremental" in args
    summary_mode = "--summary" in args
    history_mode = "--history" in args
    scan_mode = "--scan" in args
    export_risk_mode = "--export-risk" in args

    # --repos: 提取跨仓库路径列表
    cross_repo_paths: List[str] = []
    for i, arg in enumerate(args):
        if arg == "--repos" and i + 1 < len(args):
            cross_repo_paths = [p.strip() for p in args[i + 1].split(",")]
            break

    # 第一个非 flag 参数是项目路径
    project_path = None
    for arg in args:
        if not arg.startswith("-"):
            project_path = arg
            break

    if project_path is None:
        print(json.dumps({
            "error": "请指定项目路径。用法: python analyze.py <project_root>",
        }, indent=2, ensure_ascii=False))
        sys.exit(1)

    project_root = Path(project_path).resolve()
    if not project_root.is_dir():
        print(json.dumps({
            "error": f"Not a directory: {project_root}",
            "stats": _empty_stats()
        }, indent=2, ensure_ascii=False))
        sys.exit(1)

    if not (project_root / ".git").is_dir():
        print(
            f"Error: '{project_root}' 不是 git 仓库。\n"
            "Test Shield 需要 git diff 来分析代码改动。\n"
            "请在 git 仓库中运行：\n"
            "  cd your-python-project\n"
            "  python path/to/analyze.py .",
            file=sys.stderr
        )
        sys.exit(1)

    # --scan 模式：项目风险热力图（独立模式，不需要 diff）
    if scan_mode:
        print("正在扫描项目风险...", file=sys.stderr)
        heatmap = _scan_project(project_root)
        output = {
            "mode": "scan",
            "project": str(project_root),
            "total_files_scanned": len(heatmap),
            "heatmap": heatmap,
            "summary": {
                "critical": sum(1 for h in heatmap if h["risk_level"] == "critical"),
                "high": sum(1 for h in heatmap if h["risk_level"] == "high"),
                "medium": sum(1 for h in heatmap if h["risk_level"] == "medium"),
                "low": sum(1 for h in heatmap if h["risk_level"] == "low"),
            }
        }
        if summary_mode:
            _print_heatmap(output)
        elif export_risk_mode:
            print(json.dumps(_export_anonymized_risk_for_scan(output),
                             indent=2, ensure_ascii=False))
        else:
            print(json.dumps(output, indent=2, ensure_ascii=False))
        return

    diff_text = run_git_diff(project_root)
    changed_files = parse_diff_files(diff_text)
    changed_functions = find_changed_functions(project_root, changed_files)
    affected_callers = build_call_graph(
        project_root, changed_functions, incremental=incremental_mode
    )
    dynamic_risks = detect_dynamic_risks(project_root)

    # 跨仓库追踪
    cross_repo_callers = []
    if cross_repo_paths and changed_functions:
        cross_repo_callers = _cross_repo_search(
            project_root, changed_functions, cross_repo_paths
        )

    git_history = _analyze_git_history(project_root, changed_functions) if history_mode else []
    behavior_suggestions = (
        _behavioral_diff_suggestion(changed_functions, project_root)
        if history_mode else []
    )

    seen = set()
    unique_callers = []
    for c in affected_callers:
        key = (c["caller_file"], c["caller_line"], c["callee_name"])
        if key not in seen:
            seen.add(key)
            unique_callers.append(c)

    # 最小安全集分类
    unique_callers = _classify_criticality(unique_callers, changed_functions)

    high_risk = [c for c in unique_callers if c["risk"] == "high"]
    low_risk = [c for c in unique_callers if c["risk"] == "low"]
    high_risk_untested = [c for c in high_risk if not c["has_tests"]]
    must_test = [c for c in high_risk_untested if c.get("criticality") == "must"]
    should_test = [c for c in high_risk_untested if c.get("criticality") == "should"]

    # --pre-commit 模式（含最小安全集提示）
    if pre_commit_mode:
        if high_risk_untested:
            print(
                f"⛔ 提交被阻止：你的改动影响了 {len(high_risk_untested)} 个"
                f"高风险调用方，它们没有测试保护。\n",
                file=sys.stderr
            )
            # 最小安全集：先展示必须测的
            if must_test:
                print("  [最小安全集 — 必须测]", file=sys.stderr)
                for c in must_test[:5]:
                    print(
                        f"    {c['caller_name']}() - "
                        f"{c['caller_file']}:{c['caller_line']}",
                        file=sys.stderr
                    )
            if should_test:
                print(f"  [建议测 — {len(should_test)} 个]", file=sys.stderr)
            remaining = [c for c in high_risk_untested
                        if c.get("criticality") not in ("must", "should")]
            if remaining:
                print(f"  [可选 — {len(remaining)} 个]", file=sys.stderr)
            print(
                f"\n  最小安全集: 补 {len(must_test) + len(should_test)} 个测试即可安全合入\n"
                f"  跳过检查：git commit --no-verify\n"
                f"  生成回归测试：运行 /test-shield\n"
                f"  查看详情：python analyze.py .",
                file=sys.stderr
            )
            sys.exit(1)
        else:
            sys.exit(0)

    output = {
        "changed_functions": changed_functions,
        "affected_callers": unique_callers,
        "dynamic_risks": dynamic_risks,
        "honesty_report": {
            "tracing_method": (
                "AST static analysis + git grep pre-filter"
                if incremental_mode else "AST static analysis (full scan)"
            ),
            "test_coverage_verification": "not run (use pytest-cov after test generation)",
            "dynamic_risks_detected": len(dynamic_risks),
            "known_blind_spots": [
                "getattr(obj, 'method') - dynamic attribute access",
                "importlib.import_module() - dynamic imports",
                "decorator-injected functions",
                "monkey-patching at runtime",
            ],
        },
        "stats": {
            "total_changed_files": len(changed_files),
            "total_changed_functions": len(changed_functions),
            "total_affected_callers": len(unique_callers),
            "high_risk_count": len(high_risk),
            "low_risk_count": len(low_risk),
            "high_risk_untested_count": len(high_risk_untested),
            "dynamic_risk_count": len(dynamic_risks),
            "minimal_safe_set": {
                "must_test": len(must_test),
                "should_test": len(should_test),
                "optional": len(high_risk_untested) - len(must_test) - len(should_test),
            },
        }
    }

    if history_mode and git_history:
        output["git_archaeology"] = git_history
        output["behavioral_diff"] = behavior_suggestions

    if cross_repo_callers:
        output["cross_repo_callers"] = cross_repo_callers

    if export_risk_mode:
        anon = _export_anonymized_risk(output)
        print(json.dumps(anon, indent=2, ensure_ascii=False))
    elif summary_mode:
        _print_summary(output)
    else:
        print(json.dumps(output, indent=2, ensure_ascii=False))


def _print_summary(output: dict) -> None:
    """人类可读的摘要输出。"""
    cf = output["changed_functions"]
    callers = output["affected_callers"]
    s = output["stats"]
    hr = output["honesty_report"]

    print()
    if cf:
        changed_file = cf[0]["file"]
        print(f"  你改动了 {changed_file}:")
        for f in cf:
            print(f"    {f['name']}() L{f['line_start']}-{f['line_end']}")
    else:
        print("  未检测到函数级改动。")

    print(f"\n  间接影响 {len(callers)} 个调用方:")
    if callers:
        for c in callers:
            icon = "[HIGH]" if c["risk"] == "high" else "[LOW] "
            test_status = "[有测试]" if c["has_tests"] else "[无测试]"
            print(
                f"    {icon} {c['caller_name']}()"
                f" - {c['caller_file']}:{c['caller_line']}"
                f"  {test_status}"
            )
    else:
        print("    (无间接影响 - 这个改动没有下游调用方)")

    print(f"\n  高风险且无测试: {s['high_risk_untested_count']} 个"
          f"{' <- 提交前建议生成回归测试' if s['high_risk_untested_count'] else ''}")

    # 最小安全集
    mss = s.get("minimal_safe_set", {})
    if mss.get("must_test", 0) + mss.get("should_test", 0) > 0:
        print(f"\n  --- 最小安全集 ---")
        print(f"  [必须测] {mss['must_test']} 个 - 直接用户触达面")
        print(f"  [建议测] {mss['should_test']} 个 - 间接用户触达")
        print(f"  [可选]   {mss['optional']} 个 - 内部工具/报表")
        print(f"  补 {mss['must_test'] + mss['should_test']} 个测试即可安全合入")

    # Git 考古
    if output.get("git_archaeology"):
        print(f"\n  --- Git 考古 ---")
        for gh in output["git_archaeology"]:
            icon = "!!" if gh["risk_score"] >= 70 else "! " if gh["risk_score"] >= 40 else "~ " if gh["risk_score"] >= 15 else "  "
            print(
                f"  {icon} {gh['function']}() - "
                f"risk {gh['risk_score']}/100 ({gh['risk_level']})"
            )
            if gh["total_commits"] > 0:
                print(
                    f"     历史: {gh['total_commits']} 次修改, "
                    f"{gh['risky_commits']} 次出过 bug"
                )
            if gh["recent_risky"]:
                print(f"     最近: {gh['recent_risky'][0][:70]}")

    # 行为 Diff
    if output.get("behavioral_diff"):
        print(f"\n  --- 行为 Diff 建议 ---")
        for bd in output["behavioral_diff"]:
            print(f"  {bd['function']}({', '.join(bd['args'])})")
            print(f"    建议输入: {', '.join(bd['suggested_inputs'][:2])}")

    # 跨仓库
    if output.get("cross_repo_callers"):
        cr = output["cross_repo_callers"]
        print(f"\n  --- 跨仓库追踪: {len(cr)} 个外部调用方 ---")
        for c in cr[:5]:
            print(f"  {c['callee_name']}() -> {c['caller_repo']}/{c['caller_file']}")
        if len(cr) > 5:
            print(f"  ... 另外 {len(cr) - 5} 个")

    print(f"\n  --- 诚实声明 ---")
    print(f"  追踪方式: {hr['tracing_method']}")
    print(f"  动态风险: {hr['dynamic_risks_detected']} 处")
    if hr['dynamic_risks_detected'] > 0:
        for dr in output["dynamic_risks"]:
            print(f"    ! {dr['file']}:{dr['line']} - {dr['pattern']}")
    print(f"  已知盲点: {', '.join(hr['known_blind_spots'][:2])}...")
    print()


def _install_pre_commit_hook() -> None:
    """在 .git/hooks/pre-commit 中安装 Test Shield 检查。"""
    cwd = Path.cwd()
    git_dir = cwd / ".git"
    if not git_dir.is_dir():
        print("Error: 当前目录不是 git 仓库的根目录。", file=sys.stderr)
        print("请在 git 仓库根目录运行：python analyze.py --install-hook", file=sys.stderr)
        sys.exit(1)

    hooks_dir = git_dir / "hooks"
    hooks_dir.mkdir(exist_ok=True)
    hook_path = hooks_dir / "pre-commit"

    analyze_path = Path(__file__).resolve()
    hook_content = f"""#!/bin/bash
# Test Shield — pre-commit hook
# 安装方式：python {analyze_path} --install-hook
# 跳过检查：git commit --no-verify

python "{analyze_path}" . --pre-commit
"""

    # 如果已有 hook，追加而非覆盖
    if hook_path.exists():
        existing = hook_path.read_text()
        if "test-shield" in existing.lower() or "test_shield" in existing.lower():
            print("Test Shield pre-commit hook 已安装。")
            print(f"  位置: {hook_path}")
            return
        # 备份原 hook，追加 Test Shield
        backup_path = hook_path.with_name(hook_path.name + ".backup")
        hook_path.rename(backup_path)
        hook_content = (
            f"#!/bin/bash\n"
            f"# 原 pre-commit hook 备份在 {backup_path.name}\n"
            f"# === 原 hook ===\n"
            f"{existing}\n"
            f"# === Test Shield ===\n"
            f'python "{analyze_path}" . --pre-commit\n'
        )

    hook_path.write_text(hook_content)
    # Unix: chmod +x; Windows: 无需（git bash 能执行）
    try:
        hook_path.chmod(0o755)
    except Exception:
        pass

    print("Test Shield pre-commit hook 已安装。")
    print(f"  位置: {hook_path}")
    print(f"  以后每次 git commit 都会自动运行 Test Shield。")
    print(f"  跳过检查：git commit --no-verify")


def _empty_stats() -> dict:
    return {
        "total_changed_files": 0,
        "total_changed_functions": 0,
        "total_affected_callers": 0,
        "high_risk_count": 0,
        "low_risk_count": 0,
        "high_risk_untested_count": 0,
        "dynamic_risk_count": 0,
    }


def _print_usage() -> None:
    print("Usage: python analyze.py <project_root>", file=sys.stderr)
    print("       python analyze.py --help", file=sys.stderr)


def _print_help() -> None:
    print(f"""test-shield v{__version__} - AST 调用链追踪脚本

用法:
    python analyze.py <project_root>              完整分析（全量 AST 扫描）
    python analyze.py <project_root> --summary     人类可读摘要
    python analyze.py <project_root> --pre-commit  pre-commit 检查（退出码 1=阻止）
    python analyze.py <project_root> --incremental 增量分析（大型项目推荐）
    python analyze.py <project_root> --history     完整分析 + Git考古 + 行为Diff建议
    python analyze.py <project_root> --scan        项目风险热力图（全量扫描，无需 diff）
    python analyze.py <project_root> --repos R1,R2 跨仓库追踪（在关联仓库中搜索调用方）
    python analyze.py <project_root> --export-risk 导出匿名风险数据（可安全分享）
    python analyze.py --install-hook              一键安装 .git/hooks/pre-commit
    python analyze.py --version                   显示版本号
    python analyze.py --help                      显示此帮助

示例:
    cd ~/my-python-project

    # 看看改动了什么、影响了谁
    python path/to/analyze.py . --summary

    # 提交前检查
    python path/to/analyze.py . --pre-commit

    # 永久装上 pre-commit hook
    python path/to/analyze.py --install-hook

    # 大型项目用增量模式
    python path/to/analyze.py . --incremental

    # 完整分析 + Git 考古 + 行为 Diff
    python path/to/analyze.py . --history --summary

    # 项目风险热力图
    python path/to/analyze.py . --scan --summary

    # 跨仓库追踪（修改共享库后检查下游服务）
    python path/to/analyze.py . --repos ../service-a,../service-b

    # 导出匿名风险数据
    python path/to/analyze.py . --export-risk

pre-commit 模式:
    高风险 + 无测试调用方 → exit 1，阻止提交
    全部安全 → exit 0，静默放行

增量模式:
    git grep 预筛选 → 只解析相关文件。1000 文件项目改 1 个函数 → <1 秒。

零依赖。纯 Python stdlib (ast + json + subprocess)。Python 3.10+。
""")


if __name__ == "__main__":
    main()
