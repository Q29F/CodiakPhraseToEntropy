"""Symbolic field and a character-frequency adapter for its numeric phase.

The field is an illustrative signed model. A separate phrase adapter computes
Shannon entropy from NFC-normalized character frequencies, then maps entropy
divided by log2(text length) to a phase. It preserves case and whitespace;
character order has no effect on the frequency analysis.
"""

from __future__ import annotations

import csv
import math
import unicodedata
from collections import Counter
from numbers import Real
from os import PathLike
from pathlib import Path

import sympy as sp


PHASE_MAX = math.pi
MAX_PHRASE_LENGTH = 2048
x, y, t = sp.symbols("x y t", real=True)
u = sp.Function("u", real=True)(x, y, t)
v = sp.Function("v", real=True)(x, y, t)


def analyze_phrase(text: str) -> dict[str, int | float]:
    """Map NFC character frequencies to a length-normalized phase in [0, pi].

    Length is measured in Unicode code points before and after normalization.
    Repeating text can change its normalized entropy even when the character
    probabilities stay the same. The returned analysis contains no raw text.
    """
    if not isinstance(text, str):
        raise TypeError("phrase must be a string")
    if len(text) > MAX_PHRASE_LENGTH:
        raise ValueError("phrase must contain at most 2048 Unicode code points")
    if any(0xD800 <= ord(character) <= 0xDFFF for character in text):
        raise ValueError("phrase must not contain surrogate code points")

    normalized_text = unicodedata.normalize("NFC", text)
    if len(normalized_text) > MAX_PHRASE_LENGTH:
        raise ValueError("normalized phrase must contain at most 2048 Unicode code points")
    length = len(normalized_text)
    counts = Counter(normalized_text)
    unique = len(counts)
    if unique <= 1:
        entropy_bits = 0.0
        normalized_entropy = 0.0
    else:
        probabilities = (count / length for count in counts.values())
        entropy_bits = -math.fsum(probability * math.log2(probability) for probability in probabilities)
        normalized_entropy = min(1.0, max(0.0, entropy_bits / math.log2(length)))
    return {
        "length": length,
        "unique": unique,
        "entropy": entropy_bits,
        "normalizedEntropy": normalized_entropy,
        "phase": math.pi * normalized_entropy,
    }


def validate_phase(phase: Real) -> float:
    """Normalize a finite real numeric phase in [0, pi] to a Python float.

    Boolean and string inputs are rejected rather than coerced. The supported
    input types are numbers.Real implementations, including int and float.
    """
    if isinstance(phase, bool) or not isinstance(phase, Real):
        raise TypeError("phase must be a real number, not a boolean or string")
    # Check the original value as well as its float conversion, so a negative
    # value that underflows to -0.0 cannot bypass the lower bound.
    if phase < 0 or phase > PHASE_MAX:
        raise ValueError("phase must be between 0 and pi radians, inclusive")
    try:
        numeric_phase = float(phase)
    except (OverflowError, ValueError) as error:
        raise ValueError("phase must be finite") from error
    if not math.isfinite(numeric_phase):
        raise ValueError("phase must be finite")
    return numeric_phase


def build_expression(phase: Real = 0) -> sp.Expr:
    """Return sqrt(u**2 + v**2) * sin(x*y + t + phase).

    Phase zero retains the exact original symbolic expression. Nonzero phases
    use the validated floating-point value, as supplied by the notebook slider.
    """
    numeric_phase = validate_phase(phase)
    symbolic_phase = sp.Integer(0) if numeric_phase == 0 else sp.Float(numeric_phase)
    return sp.sqrt(u**2 + v**2) * sp.sin(x * y + t + symbolic_phase)


def export_csv(path: str | PathLike[str], phase: Real = 0) -> Path:
    """Write one CSV row containing the current phase and symbolic expression.

    Validation happens before opening the destination. An explicit call writes
    or overwrites the requested file; imports never create files. Filesystem
    errors propagate to the caller, and parent directories are not created.
    """
    numeric_phase = validate_phase(phase)
    expression = build_expression(numeric_phase)
    destination = Path(path)
    with destination.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=("phase", "expression"))
        writer.writeheader()
        writer.writerow({"phase": numeric_phase, "expression": str(expression)})
    return destination
