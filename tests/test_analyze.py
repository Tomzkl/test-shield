"""
Test Shield — analyze.py 单元测试
测试自己的测试工具。
"""
import ast
import json
import os
import sys
import tempfile
import textwrap
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
import analyze


class TestMergeLineRanges:
    def test_empty_returns_empty(self):
        assert analyze.merge_line_ranges([]) == []

    def test_single_range_unchanged(self):
        assert analyze.merge_line_ranges([(1, 5)]) == [(1, 5)]

    def test_non_overlapping_kept_separate(self):
        result = analyze.merge_line_ranges([(1, 5), (10, 15)])
        assert result == [(1, 5), (10, 15)]

    def test_overlapping_merged(self):
        result = analyze.merge_line_ranges([(1, 10), (5, 15)])
        assert result == [(1, 15)]

    def test_adjacent_merged(self):
        result = analyze.merge_line_ranges([(1, 5), (6, 10)])
        assert result == [(1, 10)]

    def test_multiple_overlapping_merged(self):
        result = analyze.merge_line_ranges([(1, 3), (2, 8), (7, 12)])
        assert result == [(1, 12)]


class TestParseDiffFiles:
    def test_empty_diff_returns_empty(self):
        assert analyze.parse_diff_files("") == []

    def test_single_file_diff(self):
        diff = textwrap.dedent("""\
        diff --git a/src/foo.py b/src/foo.py
        index abc..def 100644
        --- a/src/foo.py
        +++ b/src/foo.py
        @@ -10,3 +10,5 @@
         old line
        +new line 1
        +new line 2
         unchanged
        """)
        result = analyze.parse_diff_files(diff)
        assert len(result) == 1
        assert result[0]["file"] == "src/foo.py"
        assert len(result[0]["added_lines"]) > 0

    def test_multiple_files(self):
        diff = textwrap.dedent("""\
        diff --git a/a.py b/a.py
        @@ -1,1 +1,2 @@
        +added
        diff --git a/b.py b/b.py
        @@ -5,1 +5,3 @@
        +added1
        +added2
        """)
        result = analyze.parse_diff_files(diff)
        assert len(result) == 2


class TestIsLowRisk:
    def test_logger_calls_are_low_risk(self):
        assert analyze.is_low_risk("logger.info", "src/foo.py") is True
        assert analyze.is_low_risk("log.error", "src/foo.py") is True

    def test_assert_methods_are_low_risk(self):
        assert analyze.is_low_risk("assertEqual", "tests/test_foo.py") is True
        assert analyze.is_low_risk("self.assertTrue", "tests/test_foo.py") is True

    def test_dunder_methods_are_low_risk(self):
        assert analyze.is_low_risk("__repr__", "src/models.py") is True
        assert analyze.is_low_risk("__str__", "src/models.py") is True

    def test_business_logic_is_high_risk(self):
        assert analyze.is_low_risk("calculate_total", "src/cart.py") is False
        assert analyze.is_low_risk("process_payment", "src/payment.py") is False

    def test_utils_dir_is_low_risk(self):
        assert analyze.is_low_risk("helper_func", "src/utils/helpers.py") is True

    def test_metrics_dir_is_low_risk(self):
        assert analyze.is_low_risk("counter", "src/metrics/stats.py") is True


class TestFindEnclosingFunction:
    def test_finds_enclosing_function(self):
        source = textwrap.dedent("""\
        def outer():
            x = 1
            def inner():
                call_target()  # line 4
            inner()
        """)
        tree = ast.parse(source)
        result = analyze.find_enclosing_function(tree, 4)
        assert result is not None
        assert result.name == "inner"

    def test_returns_none_for_module_level(self):
        source = "call_target()\n"
        tree = ast.parse(source)
        result = analyze.find_enclosing_function(tree, 1)
        assert result is None


class TestBuildImportAliasMap:
    def test_simple_alias(self):
        source = "from chess_utils import is_checkmate as check_mate\n"
        tree = ast.parse(source)
        alias_map = analyze.build_import_alias_map(tree)
        assert alias_map == {"check_mate": "is_checkmate"}

    def test_multiple_aliases(self):
        source = textwrap.dedent("""\
        from chess_utils import is_checkmate as cm, is_in_check as ic
        from models import User as U
        """)
        tree = ast.parse(source)
        alias_map = analyze.build_import_alias_map(tree)
        assert alias_map == {"cm": "is_checkmate", "ic": "is_in_check", "U": "User"}

    def test_no_alias_no_entry(self):
        source = "from chess_utils import is_checkmate\n"
        tree = ast.parse(source)
        alias_map = analyze.build_import_alias_map(tree)
        assert alias_map == {}

    def test_direct_import_alias(self):
        source = "import numpy as np\n"
        tree = ast.parse(source)
        alias_map = analyze.build_import_alias_map(tree)
        assert alias_map == {"np": "numpy"}


class TestDetectDynamicRisks:
    def test_no_dynamic_calls_returns_empty(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "test.py"
            py_file.write_text("def foo(): return 1\n")
            result = analyze.detect_dynamic_risks(Path(tmpdir))
            assert result == []

    def test_getattr_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "test.py"
            py_file.write_text('getattr(obj, "method_name")\n')
            result = analyze.detect_dynamic_risks(Path(tmpdir))
            assert any("getattr" in r["pattern"] for r in result)

    def test_importlib_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            py_file = Path(tmpdir) / "test.py"
            py_file.write_text('importlib.import_module("some.module")\n')
            result = analyze.detect_dynamic_risks(Path(tmpdir))
            assert any("importlib" in r["pattern"] for r in result)


class TestCheckHasTests:
    def test_no_test_dir_returns_false(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            result = analyze.check_has_tests(Path(tmpdir), "my_function")
            assert result is False

    def test_function_name_found_in_test(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "tests"
            test_dir.mkdir()
            test_file = test_dir / "test_foo.py"
            test_file.write_text("def test_my_function(): pass\n")
            result = analyze.check_has_tests(Path(tmpdir), "my_function")
            assert result is True


class TestFindChangedFunctions:
    def test_changed_function_detected(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "src").mkdir(parents=True)
            py_file = Path(tmpdir) / "src" / "foo.py"
            py_file.write_text(textwrap.dedent("""\
                def unchanged():
                    pass

                def changed_func():
                    return 42

                def also_unchanged():
                    pass
                """))
            changed_files = [{
                "file": "src/foo.py",
                "added_lines": [(4, 6)]  # changed_func range
            }]
            result = analyze.find_changed_functions(Path(tmpdir), changed_files)
            assert len(result) == 1
            assert result[0]["name"] == "changed_func"
            assert result[0]["line_start"] == 4


class TestEndToEnd:
    """端到端测试：模拟真实工作流。"""

    def test_full_pipeline_with_temp_project(self):
        """在临时项目中模拟改动 → 追踪 → 验证。"""
        with tempfile.TemporaryDirectory() as tmpdir:
            project = Path(tmpdir)

            # 初始化 git
            os.system(f"cd {project} && git init -q && git config user.email 'test@test.com' && git config user.name 'test'")

            # 创建被调用的模块
            lib_dir = project / "lib"
            lib_dir.mkdir()
            (lib_dir / "__init__.py").touch()
            (lib_dir / "core.py").write_text(textwrap.dedent("""\
                def calculate_discount(price, coupon):
                    if coupon == 0:
                        return price
                    return price - coupon
                """), encoding="utf-8")

            # 创建调用方模块（使用别名 import）
            src_dir = project / "src"
            src_dir.mkdir()
            (src_dir / "__init__.py").touch()
            (src_dir / "checkout.py").write_text(textwrap.dedent("""\
                from lib.core import calculate_discount as calc_discount

                def checkout(price, coupon):
                    return calc_discount(price, coupon)
                """), encoding="utf-8")

            # 初始提交
            os.system(f"cd {project} && git add -A && git commit -q -m 'init'")

            # 改动：修改 calculate_discount 函数
            (lib_dir / "core.py").write_text(textwrap.dedent("""\
                def calculate_discount(price, coupon):
                    if coupon == 0:
                        return price
                    if coupon > price:
                        return 0  # <-- 新增守卫
                    return price - coupon
                """), encoding="utf-8")

            # 运行 analyze.py
            import subprocess
            result = subprocess.run(
                [sys.executable, str(Path(__file__).parent.parent / "scripts" / "analyze.py"), str(project)],
                capture_output=True, text=True, encoding="utf-8"
            )
            assert result.returncode == 0

            data = json.loads(result.stdout)
            assert "error" not in data

            # 验证：检测到 changed function
            assert len(data["changed_functions"]) == 1
            assert data["changed_functions"][0]["name"] == "calculate_discount"

            # 验证：检测到 alias 调用方（calc_discount → calculate_discount）
            assert len(data["affected_callers"]) >= 1
            caller_names = [c["caller_name"] for c in data["affected_callers"]]
            assert "checkout" in caller_names

            # 验证：stats 合理
            assert data["stats"]["total_changed_functions"] == 1
            assert data["stats"]["total_affected_callers"] >= 1
