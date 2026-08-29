"""Regime classification (V1.5C): the growth x inflation quadrant map.

Driven ONLY by the two factor results (which themselves read only signal
outputs). All thresholds come from ``config/macro.yaml`` ``regime`` /
``confidence`` sections - nothing is hardcoded.

Evaluation order (first match wins, mirroring the config comments):

1. ``NO_SIGNAL``       - growth or inflation has no computable signals;
2. ``LOW_CONFIDENCE``  - both computable, but the lower factor confidence
                         composite is below ``min_confidence``;
3. ``TRANSITION``      - at least one axis has |score| <= score_threshold;
4. quadrant            - both axes beyond the threshold (Reflation /
                         Goldilocks / Stagflation / Deflationary Slowdown)
                         unless breadth support is too thin;
5. ``MIXED``           - the quadrant direction is supported by fewer than
                         ``min_breadth`` mechanisms on either axis.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Mapping, Optional

from macro_compass.macro.factors import FactorResult

QUADRANTS = {
    ("up", "up"): "Reflation",
    ("up", "down"): "Goldilocks",
    ("down", "up"): "Stagflation",
    ("down", "down"): "Deflationary Slowdown",
}


@dataclass
class RegimeResult:
    """The classified regime plus its full, inspectable rationale."""

    regime: str
    growth_score: Optional[float]
    inflation_score: Optional[float]
    growth_state: str  # up / down / neutral / none
    inflation_state: str
    rationale: list[str] = field(default_factory=list)


def _axis_state(score: Optional[float], threshold: float) -> str:
    if score is None:
        return "none"
    if score > threshold:
        return "up"
    if score < -threshold:
        return "down"
    return "neutral"


def classify_regime(
    factors: Mapping[str, FactorResult], macro_config: Mapping
) -> RegimeResult:
    """Classify the macro regime from the growth and inflation factor results."""
    regime_cfg = macro_config["regime"]
    threshold = float(regime_cfg["score_threshold"])
    min_breadth = int(regime_cfg["min_breadth"])
    min_confidence = float(macro_config["confidence"]["min_confidence"])

    growth = factors.get("growth")
    inflation = factors.get("inflation")
    growth_score = growth.score if growth is not None else None
    inflation_score = inflation.score if inflation is not None else None
    growth_state = _axis_state(growth_score, threshold)
    inflation_state = _axis_state(inflation_score, threshold)
    rationale: list[str] = [
        f"growth score {growth_score if growth_score is None else round(growth_score, 3)} "
        f"-> {growth_state}; "
        f"inflation score {inflation_score if inflation_score is None else round(inflation_score, 3)} "
        f"-> {inflation_state} (threshold +/-{threshold})",
    ]

    def done(regime: str, *lines: str) -> RegimeResult:
        return RegimeResult(
            regime=regime,
            growth_score=growth_score,
            inflation_score=inflation_score,
            growth_state=growth_state,
            inflation_state=inflation_state,
            rationale=[*rationale, *lines],
        )

    if growth_score is None or inflation_score is None:
        missing = "growth" if growth_score is None else "inflation"
        return done(
            "NO_SIGNAL",
            f"the {missing} factor has no computable signals - regime undefined",
        )

    if growth is not None and inflation is not None:
        confidence = min(
            growth.confidence.get("composite", 0.0),
            inflation.confidence.get("composite", 0.0),
        )
        rationale.append(
            f"lowest factor confidence {round(confidence, 3)} vs min_confidence {min_confidence}"
        )
        if confidence < min_confidence:
            return done("LOW_CONFIDENCE", "confidence too low to call a quadrant")

    if "neutral" in (growth_state, inflation_state):
        return done(
            "TRANSITION", "at least one axis is inside the score threshold band"
        )

    quadrant = QUADRANTS[(growth_state, inflation_state)]
    weak = [
        name
        for name, result, state in (
            ("growth", growth, growth_state),
            ("inflation", inflation, inflation_state),
        )
        if result is not None and result.breadth < min_breadth
    ]
    rationale.append(
        f"breadth: growth {growth.breadth if growth else 0}, "
        f"inflation {inflation.breadth if inflation else 0} (min_breadth {min_breadth})"
    )
    if weak:
        return done(
            "MIXED",
            f"quadrant {quadrant} indicated but {'/'.join(weak)} breadth too thin "
            "to confirm the direction",
        )
    return done(quadrant)
