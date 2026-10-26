"""Behavioral regression tests; run with python -m unittest discover -s tests -v."""

import csv
from contextlib import chdir
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

import sympy as sp

import entropy


ROOT = Path(__file__).resolve().parents[1]


def read_export(path):
    """Read the public CSV format, including its comma-containing expression."""
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        return reader.fieldnames, rows


def stored_expression(text):
    return sp.sympify(text, locals={
        "x": entropy.x, "y": entropy.y, "t": entropy.t,
        "u": entropy.u.func, "v": entropy.v.func,
    })


class ExpressionTests(unittest.TestCase):
    def test_all_python_sources_compile(self):
        # The original .py files failed here on unquoted prose at line two.
        for source in ("entropy.py", "simulation.py", "simulationV2.py", "workbench.py", "localServer.py", "web.py"):
            with self.subTest(source=source):
                path = ROOT / source
                compile(path.read_text(encoding="utf-8"), str(path), "exec")

    def test_notebook_code_cells_compile_with_the_current_module_names(self):
        path = ROOT / "CodiakPhraseToEntropySimulationV2.ipynb"
        notebook = json.loads(path.read_text(encoding="utf-8"))
        for index, cell in enumerate(notebook["cells"]):
            if cell["cell_type"] == "code":
                source = "".join(cell["source"])
                with self.subTest(cell=index):
                    compile(source, f"{path.name}:cell{index}", "exec")

    def test_symbolic_formula_at_known_phases(self):
        magnitude = sp.sqrt(entropy.u ** 2 + entropy.v ** 2)
        for phase in (0, 0.5, math.pi / 2, math.pi):
            with self.subTest(phase=phase):
                expected = magnitude * sp.sin(entropy.x * entropy.y + entropy.t + phase)
                actual = entropy.build_expression(phase)
                self.assertEqual(sp.simplify(actual - expected), 0)

    def test_squared_fields_give_three_four_five_magnitude(self):
        for u_value, v_value in ((3, 4), (-3, 4), (3, -4), (0, 0)):
            with self.subTest(u=u_value, v=v_value):
                value = entropy.build_expression(math.pi / 2).subs({
                    entropy.u: u_value, entropy.v: v_value,
                    entropy.x: 0, entropy.y: 0, entropy.t: 0,
                }, simultaneous=True)
                self.assertAlmostEqual(float(value), math.hypot(u_value, v_value), places=12)

    def test_phase_endpoints_and_midpoint_have_expected_numeric_effect(self):
        for phase, expected in ((0, 0), (math.pi / 2, 5), (math.pi, 0)):
            with self.subTest(phase=phase):
                value = entropy.build_expression(phase).subs({
                    entropy.u: 3, entropy.v: 4,
                    entropy.x: 0, entropy.y: 0, entropy.t: 0,
                }, simultaneous=True)
                self.assertAlmostEqual(float(value), expected, places=12)

    def test_invalid_phase_types_are_rejected(self):
        for phase in (True, False, "0.5", "pi/2", "", None, 1j):
            with self.subTest(phase=repr(phase)):
                with self.assertRaises(TypeError):
                    entropy.build_expression(phase)

    def test_nonfinite_and_out_of_range_phases_are_rejected(self):
        for phase in (math.nan, math.inf, -math.inf, -0.001, math.pi + 0.001):
            with self.subTest(phase=repr(phase)):
                with self.assertRaises(ValueError):
                    entropy.build_expression(phase)


class PhraseTests(unittest.TestCase):
    def test_known_character_distributions_map_to_the_documented_phase(self):
        cases = (
            ("", 0, 0, 0, 0, 0),
            ("a", 1, 1, 0, 0, 0),
            ("ab", 2, 2, 1, 1, math.pi),
            ("abab", 4, 2, 1, 0.5, math.pi / 2),
            ("aaaa", 4, 1, 0, 0, 0),
            ("abcd", 4, 4, 2, 1, math.pi),
        )
        for phrase, length, unique, bits, normalized, phase in cases:
            with self.subTest(phrase=phrase):
                result = entropy.analyze_phrase(phrase)
                self.assertEqual(set(result), {"length", "unique", "entropy", "normalizedEntropy", "phase"})
                self.assertEqual(result["length"], length)
                self.assertEqual(result["unique"], unique)
                self.assertAlmostEqual(result["entropy"], bits, places=12)
                self.assertAlmostEqual(result["normalizedEntropy"], normalized, places=12)
                self.assertAlmostEqual(result["phase"], phase, places=12)

    def test_nonuniform_distribution_and_order_invariance(self):
        result = entropy.analyze_phrase("aaab")
        self.assertAlmostEqual(result["entropy"], 0.8112781244591328, places=12)
        self.assertAlmostEqual(result["normalizedEntropy"], 0.4056390622295664, places=12)
        self.assertAlmostEqual(result["phase"], math.pi * 0.4056390622295664, places=12)
        self.assertEqual(result, entropy.analyze_phrase("baaa"))

    def test_unicode_is_normalized_without_folding_case_or_whitespace(self):
        self.assertEqual(entropy.analyze_phrase("éa"), entropy.analyze_phrase("e\u0301a"))
        self.assertEqual(entropy.analyze_phrase("éé")["length"], 2)
        self.assertEqual(entropy.analyze_phrase("e\u0301e\u0301")["unique"], 1)
        for phrase in ("Aa", "a ", "a\n", "🌊a"):
            with self.subTest(phrase=phrase):
                result = entropy.analyze_phrase(phrase)
                self.assertEqual(result["length"], 2)
                self.assertEqual(result["unique"], 2)
                self.assertAlmostEqual(result["entropy"], 1, places=12)
                self.assertAlmostEqual(result["phase"], math.pi, places=12)

    def test_input_bounds_apply_before_and_after_unicode_normalization(self):
        self.assertEqual(entropy.analyze_phrase("a" * 2048)["length"], 2048)
        expanded = entropy.analyze_phrase("\u0344" * 1024)
        self.assertEqual(expanded["length"], 2048)
        self.assertAlmostEqual(expanded["normalizedEntropy"], 1 / 11, places=12)
        for phrase in ("a" * 2049, "e\u0301" * 1025, "\u0344" * 1025):
            with self.subTest(length=len(phrase)):
                with self.assertRaises(ValueError):
                    entropy.analyze_phrase(phrase)

    def test_wrong_types_and_surrogates_are_rejected(self):
        for phrase in (None, True, False, 1, 0.5, [], {}, b"ab"):
            with self.subTest(value=repr(phrase)):
                with self.assertRaises(TypeError):
                    entropy.analyze_phrase(phrase)
        for phrase in ("\ud800", "x\udfff", "\ud800\udc00"):
            with self.subTest(value=repr(phrase)):
                with self.assertRaises(ValueError):
                    entropy.analyze_phrase(phrase)


class ExportTests(unittest.TestCase):
    def test_export_contains_actual_expression_and_selected_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "entropy.csv"
            result = entropy.export_csv(path, phase=0.75)
            self.assertEqual(result, path)
            fields, rows = read_export(path)
            self.assertEqual(fields, ["phase", "expression"])
            self.assertEqual(len(rows), 1)
            self.assertEqual(float(rows[0]["phase"]), 0.75)
            self.assertEqual(
                sp.simplify(stored_expression(rows[0]["expression"]) - entropy.build_expression(0.75)),
                0,
            )

    def test_invalid_phase_does_not_create_or_truncate_an_export(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "entropy.csv"
            with self.assertRaises(ValueError):
                entropy.export_csv(path, phase=math.nan)
            self.assertFalse(path.exists())
            path.write_text("existing result\n", encoding="utf-8")
            for phase, error in ((math.inf, ValueError), (-1, ValueError), (True, TypeError)):
                with self.subTest(phase=repr(phase)):
                    with self.assertRaises(error):
                        entropy.export_csv(path, phase=phase)
                    self.assertEqual(path.read_text(encoding="utf-8"), "existing result\n")


class ProcessTests(unittest.TestCase):
    def run_python(self, args, cwd):
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(ROOT)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        return subprocess.run(
            [sys.executable, *args], cwd=cwd, env=environment,
            text=True, capture_output=True, timeout=30, check=False,
        )

    def test_imports_do_not_print_or_export(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_python([
                "-c", "import entropy; import simulation; import simulationV2; import workbench; import web",
            ], directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, "")
            self.assertEqual(result.stderr, "")
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_basic_cli_runs_and_does_not_export(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_python([str(ROOT / "simulation.py")], directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(entropy.build_expression(0)), result.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_v2_cli_exports_requested_phase(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "requested.csv"
            result = self.run_python([
                str(ROOT / "simulationV2.py"), "--phase", "0.8", "--export", str(path),
            ], directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(entropy.build_expression(0.8)), result.stdout)
            _, rows = read_export(path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(float(rows[0]["phase"]), 0.8)
            self.assertEqual(
                sp.simplify(stored_expression(rows[0]["expression"]) - entropy.build_expression(0.8)),
                0,
            )

    def test_v2_cli_requires_explicit_export(self):
        with tempfile.TemporaryDirectory() as directory:
            result = self.run_python([str(ROOT / "simulationV2.py")], directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn(str(entropy.build_expression(0.5)), result.stdout)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_v2_cli_derives_and_exports_the_phrase_phase_without_echoing_text(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "phrase.csv"
            result = self.run_python([
                str(ROOT / "simulationV2.py"), "--phrase", "abab", "--export", str(path),
            ], directory)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), str(entropy.build_expression(math.pi / 2)))
            fields, rows = read_export(path)
            self.assertEqual(fields, ["phase", "expression"])
            self.assertEqual(len(rows), 1)
            self.assertAlmostEqual(float(rows[0]["phase"]), math.pi / 2, places=12)
            self.assertNotIn("abab", path.read_text(encoding="utf-8"))

    def test_v2_cli_rejects_conflicting_modes_and_oversized_phrases(self):
        for arguments in (("--phrase", "ab", "--phase", "0.5"), ("--phrase", "a" * 2049)):
            with self.subTest(arguments=arguments[:2]), tempfile.TemporaryDirectory() as directory:
                result = self.run_python([str(ROOT / "simulationV2.py"), *arguments], directory)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("error:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_v2_cli_rejects_invalid_phases_without_exporting(self):
        for phase in ("nan", "inf", "-inf", "-0.01", "3.15", "not-a-number"):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / "rejected.csv"
                result = self.run_python([
                    str(ROOT / "simulationV2.py"), f"--phase={phase}", "--export", str(path),
                ], directory)
                self.assertEqual(result.returncode, 2, result.stderr)
                self.assertIn("error:", result.stderr)
                self.assertNotIn("Traceback", result.stderr)
                self.assertFalse(path.exists())


class InterfaceTests(unittest.TestCase):
    def test_default_widget_export_uses_the_current_filename(self):
        import ipywidgets as widgets
        from simulationV2 import create_interface

        with tempfile.TemporaryDirectory() as directory, chdir(directory):
            interface = create_interface()
            try:
                button = next(child for child in interface.children if isinstance(child, widgets.Button))
                self.assertEqual(list(Path(directory).iterdir()), [])
                button.click()
                path = Path(directory) / "entropy-export.csv"
                self.assertTrue(path.is_file())
                fields, rows = read_export(path)
                self.assertEqual(fields, ["phase", "expression"])
                self.assertEqual(float(rows[0]["phase"]), 0.5)
            finally:
                for child in interface.children:
                    child.close()
                interface.close()

    def test_slider_updates_expression_and_button_exports_current_phase(self):
        import ipywidgets as widgets
        from simulationV2 import create_interface

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "selected.csv"
            interface = create_interface(phase=0.5, export_path=path)
            try:
                slider = next(child for child in interface.children if isinstance(child, widgets.FloatSlider))
                expression = next(child for child in interface.children if isinstance(child, widgets.HTMLMath))
                export_button = next(child for child in interface.children if isinstance(child, widgets.Button))
                self.assertFalse(path.exists())
                before = expression.value
                slider.value = 1.25
                self.assertNotEqual(expression.value, before)
                self.assertIn(sp.latex(entropy.build_expression(1.25)), expression.value)
                self.assertFalse(path.exists(), "Changing the phase must not export implicitly")
                export_button.click()
                _, rows = read_export(path)
                self.assertEqual(len(rows), 1)
                self.assertEqual(float(rows[0]["phase"]), 1.25)
                self.assertEqual(
                    sp.simplify(stored_expression(rows[0]["expression"]) - entropy.build_expression(1.25)),
                    0,
                )
            finally:
                for child in interface.children:
                    child.close()
                interface.close()


if __name__ == "__main__":
    unittest.main()
