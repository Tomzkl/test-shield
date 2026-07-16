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
        print(json.dumps({"error": f"Git diff failed: {e}"}))
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

                for r_start, r_end in changed_ranges:
                    if func_start <= r_end and func_end >= r_start:
                        class_name = None
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
                            "message": f"{message} — {line.strip()[:80]}"
                        })

    return risks


def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "error": "Usage: python analyze.py <project_root>",
            "changed_functions": [],
            "affected_callers": [],
            "dynamic_risks": [],
            "stats": {
                "total_changed_files": 0,
                "total_changed_functions": 0,
                "total_affected_callers": 0,
                "high_risk_count": 0,
                "low_risk_count": 0,
                "dynamic_risk_count": 0
            }
        }, indent=2, ensure_ascii=False))
        sys.exit(1)

    if sys.argv[1] in ("--version", "-V", "-v"):
        print(f"test-shield v{__version__}")
        sys.exit(0)

    if sys.argv[1] in ("--help", "-h"):
        print(f"""test-shield v{__version__} — AST 调用链追踪脚本

用法:
    python analyze.py <project_root>              完整分析（全量 AST 扫描）
    python analyze.py <project_root> --pre-commit  pre-commit 检查模式
    python analyze.py <project_root> --incremental 增量分析（仅解析相关文件）
    python analyze.py --version                   显示版本号
    python analyze.py --help                      显示此帮助

示例:
    cd ~/my-python-project
    python ~/.claude/skills/test-shield/scripts/analyze.py .
    python ~/.claude/skills/test-shield/scripts/analyze.py . --pre-commit

pre-commit 模式:
    如果存在高风险 + 无测试保护的调用方 → exit 1，阻止提交
    否则 exit 0，静默放行
    用法：放到 .git/hooks/pre-commit 里

增量模式:
    先用 git grep 定位引用改动函数的 .py 文件，仅 AST 解析这些文件
    1000 文件项目只改 1 个函数 → 解析 5-20 个文件而非 1000 个

零依赖。纯 Python stdlib (ast + json + subprocess)。Python 3.10+。
""")
        sys.exit(0)

    # 解析参数
    args = sys.argv[1:]
    pre_commit_mode = "--pre-commit" in args
    incremental_mode = "--incremental" in args

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
            "changed_functions": [],
            "affected_callers": [],
            "dynamic_risks": [],
            "stats": {
                "total_changed_files": 0,
                "total_changed_functions": 0,
                "total_affected_callers": 0,
                "high_risk_count": 0,
                "low_risk_count": 0,
                "dynamic_risk_count": 0
            }
        }, indent=2, ensure_ascii=False))
        sys.exit(1)

    diff_text = run_git_diff(project_root)
    changed_files = parse_diff_files(diff_text)
    changed_functions = find_changed_functions(project_root, changed_files)
    affected_callers = build_call_graph(
        project_root, changed_functions, incremental=incremental_mode
    )
    dynamic_risks = detect_dynamic_risks(project_root)

    seen = set()
    unique_callers = []
    for c in affected_callers:
        key = (c["caller_file"], c["caller_line"], c["callee_name"])
        if key not in seen:
            seen.add(key)
            unique_callers.append(c)

    high_risk = [c for c in unique_callers if c["risk"] == "high"]
    low_risk = [c for c in unique_callers if c["risk"] == "low"]
    high_risk_untested = [c for c in high_risk if not c["has_tests"]]

    # --pre-commit 模式：检查高风险无测试调用方
    if pre_commit_mode:
        if high_risk_untested:
            print(
                f"⛔ 提交被阻止：你的改动影响了 {len(high_risk_untested)} 个"
                f"高风险调用方，它们没有测试保护。\n",
                file=sys.stderr
            )
            for c in high_risk_untested[:5]:
                print(
                    f"  {c['caller_name']}() — "
                    f"{c['caller_file']}:{c['caller_line']}",
                    file=sys.stderr
                )
            if len(high_risk_untested) > 5:
                print(
                    f"  ... 另外 {len(high_risk_untested) - 5} 个调用方",
                    file=sys.stderr
                )
            print(
                f"\n  跳过检查：git commit --no-verify",
                file=sys.stderr
            )
            print(
                f"  生成回归测试：运行 /test-shield",
                file=sys.stderr
            )
            print(
                f"  查看详情：python analyze.py .",
                file=sys.stderr
            )
            sys.exit(1)
        else:
            # 静默退出 — 所有安全
            sys.exit(0)

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
            "high_risk_untested_count": len(high_risk_untested),
            "dynamic_risk_count": len(dynamic_risks)
        }
    }

    print(json.dumps(output, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
