"""Validated controller for the local Codiak phase workbench."""

from __future__ import annotations

import math
from numbers import Real

from entropy import analyze_phrase, build_expression, validate_phase
from localServer import RequestError


SAMPLE_COUNT = 129


def numeric_control(value: object, name: str, bound: float) -> float:
    """Read a bounded JSON number without coercing strings or booleans."""
    message = f"{name} must be a finite number between -{bound:g} and {bound:g}."
    if isinstance(value, bool) or not isinstance(value, Real):
        raise RequestError(400, message)
    if value < -bound or value > bound:
        raise RequestError(400, message)
    try:
        number = float(value)
    except (OverflowError, ValueError):
        raise RequestError(400, message) from None
    if not math.isfinite(number):
        raise RequestError(400, message)
    return number


def calculate(payload: dict) -> dict:
    """Return a symbolic expression and a sampled constant-input cross-section.

    Phrase mode accepts exactly mode, phrase, u, v, y and t. Phase mode accepts
    exactly mode, phase, u, v, y and t. Duplicate JSON keys are rejected by the
    transport before this controller receives the payload.
    """
    if not isinstance(payload, dict):
        raise RequestError(400, "The request must be a JSON object.")
    mode = payload.get("mode")
    if mode not in ("phrase", "phase"):
        raise RequestError(400, "mode must be either phrase or phase.")
    source_key = "phrase" if mode == "phrase" else "phase"
    if set(payload) != {"mode", source_key, "u", "v", "y", "t"}:
        raise RequestError(400, f"Provide exactly mode, {source_key}, u, v, y and t for this calculation.")

    parameters = {
        name: numeric_control(payload[name], name, bound)
        for name, bound in (("u", 100.0), ("v", 100.0), ("y", 10.0), ("t", 100.0))
    }
    phrase_analysis = None
    if mode == "phrase":
        try:
            phrase_analysis = analyze_phrase(payload["phrase"])
        except (TypeError, ValueError) as error:
            raise RequestError(400, str(error)) from None
        phase = phrase_analysis["phase"]
    else:
        try:
            phase = validate_phase(payload["phase"])
        except (TypeError, ValueError, OverflowError):
            raise RequestError(400, "phase must be a finite number from 0 to pi.") from None

    amplitude = math.hypot(parameters["u"], parameters["v"])
    samples = []
    for index in range(SAMPLE_COUNT):
        coordinate = -math.pi + (2 * math.pi * index) / (SAMPLE_COUNT - 1)
        value = amplitude * math.sin(coordinate * parameters["y"] + parameters["t"] + phase)
        samples.append({"x": coordinate, "value": value})
    return {
        "phase": phase,
        "expression": str(build_expression(phase)),
        "parameters": parameters,
        "phraseAnalysis": phrase_analysis,
        "samples": samples,
    }
