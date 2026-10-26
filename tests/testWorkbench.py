"""Independent phrase-to-field and explicit numeric-controller regression tests."""

import copy
import math
import unittest

import sympy as sp

import entropy
from localServer import RequestError
from workbench import calculate


def manual(**changes):
    return {"mode": "phase", "phase": 0.5, "u": 3, "v": 4, "y": 1, "t": 0, **changes}


class CalculationTests(unittest.TestCase):
    def test_phrase_calculation_has_known_phase_and_full_sample_domain(self):
        result = calculate({"mode": "phrase", "phrase": "abab", "u": 3, "v": 4, "y": 1, "t": 0})
        self.assertEqual(set(result), {"phase", "expression", "parameters", "phraseAnalysis", "samples"})
        self.assertAlmostEqual(result["phase"], math.pi / 2, places=12)
        self.assertEqual(result["phraseAnalysis"]["length"], 4)
        self.assertEqual(result["phraseAnalysis"]["entropy"], 1)
        self.assertEqual(result["phraseAnalysis"]["normalizedEntropy"], 0.5)
        self.assertEqual(result["parameters"], {"u": 3, "v": 4, "y": 1, "t": 0})
        samples = result["samples"]
        self.assertEqual(len(samples), 129)
        self.assertAlmostEqual(samples[0]["x"], -math.pi, places=12)
        self.assertAlmostEqual(samples[64]["x"], 0, places=12)
        self.assertAlmostEqual(samples[-1]["x"], math.pi, places=12)
        for index, sample in enumerate(samples):
            self.assertEqual(set(sample), {"x", "value"})
            self.assertAlmostEqual(sample["x"], -math.pi + index * math.pi / 64, places=12)
            self.assertAlmostEqual(sample["value"], 5 * math.cos(sample["x"]), places=12)

    def test_numeric_samples_agree_with_independent_symbolic_substitution(self):
        symbolic_x = sp.Symbol("sample", real=True)
        fixtures = (
            manual(phase=0, u=3, v=4, y=2, t=0),
            manual(phase=math.pi / 2, u=-3, v=4, y=0, t=0),
            manual(phase=math.pi, u=1.25, v=-2.5, y=-0.75, t=0.3),
        )
        for payload in fixtures:
            with self.subTest(payload=payload):
                result = calculate(payload)
                self.assertIsNone(result["phraseAnalysis"])
                self.assertAlmostEqual(result["phase"], payload["phase"], places=12)
                expected = sp.sqrt(sp.Float(payload["u"]) ** 2 + sp.Float(payload["v"]) ** 2) * sp.sin(
                    symbolic_x * sp.Float(payload["y"]) + sp.Float(payload["t"]) + sp.Float(payload["phase"])
                )
                for index in (0, 16, 32, 64, 96, 112, 128):
                    sample = result["samples"][index]
                    self.assertAlmostEqual(sample["value"], float(expected.subs(symbolic_x, sample["x"])), places=11)
                symbolic = sp.sympify(result["expression"], locals={
                    "x": entropy.x, "y": entropy.y, "t": entropy.t,
                    "u": entropy.u.func, "v": entropy.v.func,
                })
                for index in (32, 64, 96):
                    sample = result["samples"][index]
                    displayed = symbolic.subs({
                        entropy.u: payload["u"], entropy.v: payload["v"],
                        entropy.x: sample["x"], entropy.y: payload["y"], entropy.t: payload["t"],
                    }, simultaneous=True)
                    self.assertAlmostEqual(float(displayed), sample["value"], places=11)

    def test_zero_amplitude_and_constant_cross_section_are_valid(self):
        zero = calculate(manual(u=0, v=0))
        self.assertTrue(all(sample["value"] == 0 for sample in zero["samples"]))
        constant = calculate(manual(phase=math.pi / 2, u=3, v=4, y=0))
        self.assertTrue(all(abs(sample["value"] - 5) < 1e-12 for sample in constant["samples"]))

    def test_numeric_boundaries_are_inclusive_and_finite(self):
        for sign in (-1, 1):
            with self.subTest(sign=sign):
                result = calculate(manual(phase=math.pi, u=sign * 100, v=sign * 100, y=sign * 10, t=sign * 100))
                self.assertTrue(all(math.isfinite(sample["value"]) for sample in result["samples"]))
                self.assertTrue(all(abs(sample["value"]) <= math.hypot(100, 100) + 1e-12 for sample in result["samples"]))

    def test_exact_mode_schema_is_required_without_coercion(self):
        candidates = [None, True, [], "phase", {}, {**manual(), "extra": 1}, {**manual(), "phrase": "ab"}]
        candidates.extend({key: value for key, value in manual().items() if key != missing} for missing in manual())
        candidates.extend((
            {**manual(), "mode": "unknown"},
            {"mode": "phrase", "phrase": "ab", "phase": 0, "u": 1, "v": 1, "y": 1, "t": 0},
            {"mode": "phrase", "u": 1, "v": 1, "y": 1, "t": 0},
        ))
        for payload in candidates:
            with self.subTest(payload=payload):
                with self.assertRaises(RequestError) as caught:
                    calculate(payload)
                self.assertEqual(caught.exception.status, 400)

    def test_control_bounds_types_and_nonfinite_values_are_rejected(self):
        for key, limit in (("u", 100), ("v", 100), ("y", 10), ("t", 100)):
            for value in (-limit - 0.001, limit + 0.001, math.nan, math.inf, -math.inf, True, False, "1", None, [], 1j):
                with self.subTest(control=key, value=repr(value)):
                    with self.assertRaises(RequestError) as caught:
                        calculate(manual(**{key: value}))
                    self.assertEqual(caught.exception.status, 400)
        for phase in (-0.001, math.pi + 0.001, math.nan, math.inf, True, "0.5", None):
            with self.subTest(phase=repr(phase)):
                with self.assertRaises(RequestError):
                    calculate(manual(phase=phase))

    def test_phrase_validation_and_exports_do_not_include_the_source_text(self):
        payload = {"mode": "phrase", "phrase": "<img src=x onerror=alert(1)>", "u": 1, "v": 1, "y": 1, "t": 0}
        result = calculate(payload)
        self.assertNotIn(payload["phrase"], repr(result))
        for phrase in (True, None, 1, [], "\ud800", "a" * 2049, "\u0344" * 1025):
            with self.subTest(value=repr(phrase)[:60]):
                with self.assertRaises(RequestError) as caught:
                    calculate({**payload, "phrase": phrase})
                self.assertEqual(caught.exception.status, 400)

    def test_calculation_is_deterministic_and_does_not_mutate_input(self):
        payload = manual()
        original = copy.deepcopy(payload)
        first = calculate(payload)
        self.assertEqual(payload, original)
        self.assertEqual(calculate(payload), first)
        first["parameters"]["u"] = 99
        self.assertEqual(payload, original)


if __name__ == "__main__":
    unittest.main()
