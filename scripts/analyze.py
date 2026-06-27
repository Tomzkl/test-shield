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
from typing import Dict, List, Optional, Tuple


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


def check_has_tests(project_root: Path, function_name: str) -> bool:
    """检查项目中是否已有针对该函数的测试。"""
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
            for py_file in test_path.rglob("*_test.py"):
                content = py_file.read_text(encoding="utf-8")
                if function_name in content:
                    return True
        except Exception:
            pass
    return False


def build_call_graph(
    project_root: Path, changed_functions: List[Dict]
) -> List[Dict]:
    """构建调用图：找到所有调用改动函数的代码位置。"""
    affected = []

    for py_file in project_root.rglob("*.py"):
        file_str = str(py_file.relative_to(project_root)).replace("\\", "/")

        if any(skip in py_file.parts for skip in SKIP_DIRS):
            continue

        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (SyntaxError, UnicodeDecodeError):
            continue

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
                if callee_name != changed["name"]:
                    continue

                caller_func = find_enclosing_function(tree, node.lineno)
                if caller_func:
                    caller_name_str = caller_func.name
                else:
                    caller_name_str = f"<module>:{node.lineno}"

                risk = "low" if is_low_risk(caller_name_str, file_str) else "high"

                has_tests = check_has_tests(project_root, caller_name_str)

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

    project_root = Path(sys.argv[1]).resolve()
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
    affected_callers = build_call_graph(project_root, changed_functions)
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
