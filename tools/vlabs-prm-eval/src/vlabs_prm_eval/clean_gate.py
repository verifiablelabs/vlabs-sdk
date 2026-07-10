"""Eval-card → ``CleanMetrics`` mapping + clean-gate evaluator.

The eight-condition ``CleanAcceptUpdate`` predicate itself lives in
``vlabs_sdk.formal_spec.clean_promotion_gate`` (machine-verified in
Lean 4, namespace ``Verifiable.CleanPromotionGate``). This module only handles
the schema bridge from a process-reward-model eval card (JSON dict) to
``CleanMetrics`` and the user-facing rendering — mirroring ``gate.py``.

Eval-card schema (canonical fields, all optional unless noted):

    {
      "model_id":                  "<str, required>",
      "vgs" | "composite":         <float in [0,1]>,        # raw_vgs
      "contamination_risk" | "dcr":<float in [0,1]>,        # required
      "clean_vgs":                 <float>,                  # advisory; recomputed
      "public_score":              <float in [0,1]>,
      "hidden_score":              <float in [0,1]>,
      "ood_score":                 <float in [0,1]>,
      "hack_risk":                 <float in [0,1]>,         # required
      "calibration":               <float in [0,1]>,         # required
      "cost":                      <float, $ per audit>,      # required or CLI override
      "latency":                   <float, seconds per audit>,# required or CLI override
      "regression":                <bool>                    # else derived
    }

The mapping is documented below and adjustable via the CLI ``--metrics-map``
flag (a JSON object overriding the default field names / fallbacks).
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vlabs_sdk.formal_spec.clean_promotion_gate import (
    CleanGateDecision,
    CleanMetrics,
    CleanTolerances,
    accept_clean_update,
)
from vlabs_sdk.formal_spec.clean_vgs import clean_vgs as compute_clean_vgs

# ---------------------------------------------------------------------
# Default eval-card → CleanMetrics field aliases + fallbacks
# ---------------------------------------------------------------------
DEFAULT_METRICS_MAP: dict[str, Any] = {
    # Ordered alias lists: first present key wins.
    "raw_vgs_keys": ["vgs", "composite"],
    "dcr_keys": ["contamination_risk", "dcr"],
    "clean_vgs_keys": ["clean_vgs"],
    "public_score_keys": ["public_score"],
    "hidden_score_keys": ["hidden_score"],
    "ood_score_keys": ["ood_score"],
    "hack_risk_keys": ["hack_risk"],
    "calibration_keys": ["calibration"],
    "cost_keys": ["cost"],
    "latency_keys": ["latency"],
    "regression_keys": ["regression"],
    # Retained for config-file compatibility only. Gate-critical metrics no
    # longer use optimistic defaults; missing evidence fails closed.
    "dcr_default": 0.0,
    "hack_risk_default": 0.0,
    "calibration_default": 1.0,
    "cost_default": 0.0,
    "latency_default": 0.0,
}


@dataclass(frozen=True)
class CleanEvalCard:
    """Minimal eval-card view used by the clean gate. Extra fields tolerated."""

    raw: Mapping[str, Any]

    @classmethod
    def load(cls, path: str | Path) -> CleanEvalCard:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(
                f"{path}: expected a JSON object, got {type(data).__name__}"
            )
        return cls(raw=data)

    def first(self, keys: list[str]) -> tuple[str | None, Any]:
        present = [
            (key, self.raw[key])
            for key in keys
            if key in self.raw and self.raw[key] is not None
        ]
        if not present:
            return None, None
        first_key, first_value = present[0]
        conflicting = [
            key
            for key, value in present[1:]
            if type(value) is not type(first_value) or value != first_value
        ]
        if conflicting:
            raise ValueError(
                "conflicting aliases supplied for one clean-gate metric: "
                + ", ".join([first_key, *conflicting])
            )
        return first_key, first_value


@dataclass(frozen=True)
class CleanMappingReport:
    """Diagnostic for the eval-card → CleanMetrics bridge."""

    warnings: tuple[str, ...] = field(default_factory=tuple)


def _to_float(name: str, value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name}: expected number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name}: expected a finite number")
    return result


def _to_unit_float(name: str, value: Any) -> float:
    result = _to_float(name, value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name} must be in [0, 1], got {result!r}")
    return result


def _to_nonnegative_float(name: str, value: Any) -> float:
    result = _to_float(name, value)
    if result < 0.0:
        raise ValueError(f"{name}: expected a non-negative value")
    return result


_ALIAS_POLICY_KEYS = frozenset(
    key for key in DEFAULT_METRICS_MAP if key.endswith("_keys")
)
_UNIT_DEFAULT_KEYS = frozenset(
    {"dcr_default", "hack_risk_default", "calibration_default"}
)
_NONNEGATIVE_DEFAULT_KEYS = frozenset({"cost_default", "latency_default"})
_CLEAN_MAP_KEYS = _ALIAS_POLICY_KEYS | _UNIT_DEFAULT_KEYS | _NONNEGATIVE_DEFAULT_KEYS


def _validated_metrics_map(
    metrics_map: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if metrics_map is not None and not isinstance(metrics_map, Mapping):
        raise ValueError("metrics map: expected a JSON object")
    override = dict(metrics_map or {})
    unknown = set(override) - _CLEAN_MAP_KEYS
    if unknown:
        raise ValueError(f"metrics map: unknown keys {sorted(unknown)!r}")

    resolved = dict(DEFAULT_METRICS_MAP)
    resolved.update(override)
    for key in sorted(_ALIAS_POLICY_KEYS):
        aliases = resolved[key]
        if (
            not isinstance(aliases, list)
            or not 1 <= len(aliases) <= 32
            or any(not isinstance(alias, str) or not alias.strip() for alias in aliases)
            or len(set(aliases)) != len(aliases)
        ):
            raise ValueError(
                f"{key}: expected 1..32 distinct non-empty string aliases"
            )
        resolved[key] = list(aliases)
    for key in sorted(_UNIT_DEFAULT_KEYS):
        resolved[key] = _to_unit_float(key, resolved[key])
    for key in sorted(_NONNEGATIVE_DEFAULT_KEYS):
        resolved[key] = _to_nonnegative_float(key, resolved[key])
    return resolved


def card_to_clean_metrics(
    card: CleanEvalCard,
    beta: float,
    metrics_map: Mapping[str, Any] | None = None,
    *,
    cost_override: float | None = None,
    latency_override: float | None = None,
) -> tuple[CleanMetrics, CleanMappingReport]:
    """Map an eval card onto ``CleanMetrics``.

    Returns the metrics plus a report of any compatibility warnings. Missing
    gate-critical evidence fails closed with ``ValueError``.

    ``clean_vgs`` is always recomputed from ``raw_vgs``, ``dcr`` and ``beta``
    via the machine-verified formula
    ``clean_vgs = raw_vgs*(1-dcr) - beta*dcr``. A legacy caller-supplied value
    is ignored and reported when it differs from the canonical result.
    """
    m = _validated_metrics_map(metrics_map)

    warnings: list[str] = []

    required_aliases = {
        "contamination-risk": "dcr_keys",
        "ood_score": "ood_score_keys",
        "hack_risk": "hack_risk_keys",
        "calibration": "calibration_keys",
    }
    missing = [
        label
        for label, aliases_key in required_aliases.items()
        if card.first(m[aliases_key])[0] is None
    ]
    if cost_override is None and card.first(m["cost_keys"])[0] is None:
        missing.append("cost")
    if latency_override is None and card.first(m["latency_keys"])[0] is None:
        missing.append("latency")
    if missing:
        raise ValueError(
            "missing required clean-gate fields: " + ", ".join(sorted(missing))
        )

    # ---- raw_vgs ----
    key, val = card.first(m["raw_vgs_keys"])
    if key is None:
        raise ValueError(
            f"card has none of {m['raw_vgs_keys']!r}; cannot derive raw_vgs."
        )
    raw_vgs = _to_unit_float("raw_vgs", val)

    # ---- dcr ----
    key, val = card.first(m["dcr_keys"])
    assert key is not None  # checked with the other required fields above
    dcr = _to_unit_float("dcr", val)

    # ---- clean_vgs (card value, else computed) ----
    clean_vgs_value = compute_clean_vgs(raw_vgs, dcr, beta)
    key, val = card.first(m["clean_vgs_keys"])
    if key is not None:
        supplied_clean_vgs = _to_float("clean_vgs", val)
        if not abs(supplied_clean_vgs - clean_vgs_value) <= 1e-9:
            warnings.append(
                "ignored caller-supplied clean_vgs because it differs from "
                "the canonical raw_vgs/dcr/beta computation"
            )

    # ---- public / hidden / ood scores ----
    _, pub = card.first(m["public_score_keys"])
    public_score = _to_unit_float("public_score", pub) if pub is not None else 0.0
    _, hid = card.first(m["hidden_score_keys"])
    hidden_score = _to_unit_float("hidden_score", hid) if hid is not None else 0.0
    _, ood = card.first(m["ood_score_keys"])
    assert ood is not None  # required-field check above
    ood_score = _to_unit_float("ood_score", ood)

    # ---- hack_risk ----
    key, val = card.first(m["hack_risk_keys"])
    assert key is not None  # required-field check above
    hack_risk = _to_unit_float("hack_risk", val)

    # ---- calibration ----
    key, val = card.first(m["calibration_keys"])
    assert key is not None  # required-field check above
    calibration = _to_unit_float("calibration", val)

    # ---- cost / latency ----
    if cost_override is not None:
        cost = cost_override
    else:
        key, val = card.first(m["cost_keys"])
        assert key is not None  # required-field check above
        cost = _to_float("cost", val)
    if latency_override is not None:
        latency = latency_override
    else:
        key, val = card.first(m["latency_keys"])
        assert key is not None  # required-field check above
        latency = _to_float("latency", val)

    # ---- regression (card value, else derived from contamination/calibration) ----
    key, val = card.first(m["regression_keys"])
    if key is not None:
        if not isinstance(val, bool):
            raise ValueError(f"regression: expected bool, got {val!r}")
        regression = val
    else:
        # Derived: a fully-contaminated or clearly mis-calibrated candidate is a
        # hard regression. Honest, conservative default.
        regression = bool(dcr >= 1.0 or calibration <= 0.0)

    return (
        CleanMetrics(
            raw_vgs=raw_vgs,
            dcr=dcr,
            clean_vgs=clean_vgs_value,
            public_score=public_score,
            hidden_score=hidden_score,
            ood_score=ood_score,
            hack_risk=hack_risk,
            calibration=calibration,
            cost=cost,
            latency=latency,
            regression=regression,
        ),
        CleanMappingReport(warnings=tuple(warnings)),
    )


def evaluate_clean_gate(
    old_card_path: str | Path,
    new_card_path: str | Path,
    tol: CleanTolerances,
    beta: float,
    metrics_map_path: str | Path | None = None,
    *,
    cost_old: float | None = None,
    cost_new: float | None = None,
    latency_old: float | None = None,
    latency_new: float | None = None,
) -> tuple[CleanGateDecision, CleanMetrics, CleanMetrics, list[str]]:
    """Load two cards, map to clean metrics, evaluate the clean gate.

    Returns ``(decision, old_metrics, new_metrics, warnings)``.
    """
    metrics_map: Mapping[str, Any] | None = None
    if metrics_map_path is not None:
        with open(metrics_map_path, encoding="utf-8") as f:
            metrics_map = json.load(f)

    old_card = CleanEvalCard.load(old_card_path)
    new_card = CleanEvalCard.load(new_card_path)

    old, report_old = card_to_clean_metrics(
        old_card, beta, metrics_map, cost_override=cost_old, latency_override=latency_old
    )
    new, report_new = card_to_clean_metrics(
        new_card, beta, metrics_map, cost_override=cost_new, latency_override=latency_new
    )

    warnings = [*report_old.warnings, *report_new.warnings]
    decision = accept_clean_update(tol, old, new)
    return decision, old, new, warnings


__all__ = [
    "DEFAULT_METRICS_MAP",
    "CleanEvalCard",
    "CleanMappingReport",
    "card_to_clean_metrics",
    "evaluate_clean_gate",
]
