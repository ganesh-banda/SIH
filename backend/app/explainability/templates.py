"""Deterministic English templates, keyed by evidence ``type``.

A template is a function ``values -> str | None``. It must return ``None``
if a value it needs is missing, so it can never fill a gap with a guess.

Templates for specific evidence types (fan-out, rapid movement, ...) are
added once those evidence types exist. TODO(dataset).
"""

from __future__ import annotations

from typing import Any, Callable

Template = Callable[[dict[str, Any]], str | None]

TEMPLATES: dict[str, Template] = {}


def register(evidence_type: str) -> Callable[[Template], Template]:
    def wrap(fn: Template) -> Template:
        if evidence_type in TEMPLATES:
            raise ValueError(f"Template already registered for {evidence_type!r}")
        TEMPLATES[evidence_type] = fn
        return fn
    return wrap


# --- formatting helpers (deterministic) ---------------------------------

def fmt_percent(ratio: float) -> str:
    """0.934 -> '93%'."""
    return f"{round(ratio * 100):d}%"


def fmt_duration(seconds: float) -> str:
    """120 -> '2 minutes', 45 -> '45 seconds', 5400 -> '1.5 hours'."""
    for unit, size in (("day", 86_400), ("hour", 3_600), ("minute", 60)):
        if seconds >= size:
            value = seconds / size
            text = f"{value:.1f}".rstrip("0").rstrip(".")
            return f"{text} {unit}{'' if text == '1' else 's'}"
    text = f"{seconds:.0f}"
    return f"{text} second{'' if text == '1' else 's'}"


def fmt_count(n: int, singular: str, plural: str | None = None) -> str:
    return f"{n} {singular if n == 1 else (plural or singular + 's')}"
