"""Run registered pattern detectors.

A failing detector is logged and reported, and does not stop the others.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.graph.graph_builder import TransactionGraph
from app.patterns.base import PatternDetector, PatternResult

logger = logging.getLogger(__name__)


@dataclass
class PatternRunResult:
    results: list[PatternResult] = field(default_factory=list)
    failed_detectors: dict[str, str] = field(default_factory=dict)


def run_patterns(graph: TransactionGraph, detectors: list[PatternDetector]) -> PatternRunResult:
    run = PatternRunResult()
    for detector in detectors:
        try:
            found = detector.detect(graph)
        except NotImplementedError:
            run.failed_detectors[detector.name] = "not implemented"
            continue
        except Exception as exc:  # keep other detectors running
            logger.exception("Pattern detector '%s' failed", detector.name)
            run.failed_detectors[detector.name] = type(exc).__name__
            continue
        run.results.extend(found)
        logger.info("Detector '%s': %d results", detector.name, len(found))
    return run
