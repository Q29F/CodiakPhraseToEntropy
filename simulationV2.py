"""Phase-controlled symbolic field with optional notebook controls and CSV export.

Run this file for the command-line interface. In a Jupyter notebook, call
create_interface() and display its returned widget. Importing this module does
not display an interface, import notebook packages, or write an export.
"""

from __future__ import annotations

import argparse
from collections.abc import Sequence
from html import escape
from numbers import Real
from os import PathLike
from typing import TYPE_CHECKING

from entropy import PHASE_MAX, analyze_phrase, build_expression, export_csv, validate_phase

if TYPE_CHECKING:
    import ipywidgets as widgets


def create_interface(
    phase: Real = 0.5,
    export_path: str | PathLike[str] = "entropy-export.csv",
) -> widgets.VBox:
    """Create reactive controls; only the Export CSV button writes a file.

    Notebook dependencies are loaded here rather than by command-line imports.
    The supplied export_path is a local output path selected by the caller.
    """
    numeric_phase = validate_phase(phase)
    try:
        import ipywidgets as widgets
    except ImportError as error:
        raise RuntimeError(
            "The notebook interface requires ipywidgets and IPython. "
            "Install the notebook dependencies before calling create_interface()."
        ) from error

    from sympy import latex

    introduction = widgets.HTML(
        value=(
            "<p><b>Illustrative signed symbolic field</b><br>"
            "The phase is measured in radians. The field is signed and its "
            "amplitude depends on u and v.</p>"
        )
    )
    slider = widgets.FloatSlider(
        value=numeric_phase,
        min=0.0,
        max=PHASE_MAX,
        step=0.01,
        description="Phase",
        readout_format=".3f",
        continuous_update=False,
    )
    expression = widgets.HTMLMath()
    export_button = widgets.Button(description="Export CSV", icon="download")
    status = widgets.HTML()

    def render_current_expression() -> None:
        expression.value = r"\[" + latex(build_expression(slider.value)) + r"\]"

    def phase_changed(change: dict) -> None:
        render_current_expression()
        # A previous export reflects its saved phase, not this new value.
        status.value = ""

    def export_current_expression(button: widgets.Button) -> None:
        try:
            destination = export_csv(export_path, slider.value)
        except (OSError, TypeError, ValueError) as error:
            message = str(error)
            if len(message) > 240:
                message = message[:237] + "..."
            status.value = "<b>Export failed:</b> " + escape(message)
        else:
            status.value = "<b>Saved:</b> " + escape(str(destination))

    slider.observe(phase_changed, names="value")
    export_button.on_click(export_current_expression)
    render_current_expression()
    return widgets.VBox((introduction, slider, expression, export_button, status))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Display an illustrative signed symbolic field with a numeric phase."
    )
    source = parser.add_mutually_exclusive_group()
    source.add_argument(
        "--phase", type=float, default=0.5,
        help="phase in radians between 0 and pi, inclusive (default: 0.5)",
    )
    source.add_argument(
        "--phrase", metavar="TEXT",
        help="derive phase from NFC character frequencies and normalized text length",
    )
    parser.add_argument(
        "--export", metavar="PATH",
        help="write the current phase and expression to this CSV file",
    )
    arguments = parser.parse_args(argv)
    try:
        phase = analyze_phrase(arguments.phrase)["phase"] if arguments.phrase is not None else arguments.phase
        expression = build_expression(phase)
        if arguments.export is not None:
            export_csv(arguments.export, phase)
    except (OSError, TypeError, ValueError) as error:
        parser.error(str(error))
    print(expression)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
