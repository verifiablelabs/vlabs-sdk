"""Eval-card → ``ModelMetrics`` mapping + gate evaluator.

The 7-condition ``AcceptUpdate`` predicate itself lives in
``vlabs_sdk.formal_spec.gate`` (machine-verified in Lean).
This module only handles the schema bridge from a process-reward-model
eval card (JSON dict) to ``ModelMetrics`` and the user-facing rendering.

Eval-card schema (canonical fields, all optional unless noted):

    {
      "model_id":                "<str, required>",
      "processbench_overall":    <float in [0,1]>,
      "mean_held_out_env_metric":<float in [0,1]>,
      "bon_accuracy":            <float in [0,1]>,
      "coverage":                <float in [0,1]>,
      "held_out_envs":           { "<env_name>": <float>, ... },
      "invariance_violation_rate": <float in [0,1]>,
      "cost":                    <float, $ per audit>,
      "latency":                 <float, seconds per audit>
    }

The mapping is documented in ``DEFAULT_METRICS_MAP`` and overridable
via the CLI's ``--metrics-map <path>`` flag.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from vlabs_sdk.formal_spec.gate import (
    GateDecision,
    ModelMetrics,
    Tolerances,
    accept_update,
)

# ---------------------------------------------------------------------
# Default eval-card → ModelMetrics weights
# ---------------------------------------------------------------------
DEFAULT_METRICS_MAP: dict[str, Any] = {
    "vgs_weights": {
        # Sum = 1.0. Override per checkpoint-promotion policy via
        # --metrics-map.
        "processbench_overall": 0.40,
        "mean_held_out_env_metric": 0.30,
        "bon_accuracy": 0.30,
    },
    "regression_rules": {
        # Trigger ``regression=True`` if any of these fire.
        "processbench_min": 0.60,
        "bon_lift_min": 0.05,
        "coverage_target": 0.90,
        "coverage_tol": 0.05,
    },
}


@dataclass(frozen=True)
class EvalCard:
    """Minimal eval-card view used by the gate. Extra fields are tolerated."""

    raw: Mapping[str, Any]

    @classmethod
    def load(cls, path: str | Path) -> EvalCard:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            raise ValueError(f"{path}: expected a JSON object, got {type(data).__name__}")
        return cls(raw=data)

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)


@dataclass(frozen=True)
class MappingReport:
    """Diagnostic for the eval-card → ModelMetrics bridge."""

    warnings: tuple[str, ...] = field(default_factory=tuple)


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _to_float(name: str, value: Any) -> float:
    if type(value) not in (int, float):
        raise ValueError(f"{name}: expected number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name}: expected a finite number")
    return result


def _required(card: EvalCard, name: str) -> Any:
    value = card.get(name)
    if value is None:
        raise ValueError(f"missing required gate field: {name}")
    return value


def _to_unit_float(name: str, value: Any) -> float:
    result = _to_float(name, value)
    if not 0.0 <= result <= 1.0:
        raise ValueError(f"{name}: expected a value in [0, 1]")
    return result


def _to_nonnegative_float(name: str, value: Any) -> float:
    result = _to_float(name, value)
    if result < 0.0:
        raise ValueError(f"{name}: expected a non-negative value")
    return result


_WEIGHT_KEYS = frozenset(
    {"processbench_overall", "mean_held_out_env_metric", "bon_accuracy"}
)
_REGRESSION_RULE_KEYS = frozenset(
    {"processbench_min", "bon_lift_min", "coverage_target", "coverage_tol"}
)
_METRICS_MAP_KEYS = frozenset({"vgs_weights", "regression_rules"})


def _exact_unit_mapping(
    name: str, value: Any, expected_keys: frozenset[str]
) -> dict[str, float]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{name}: expected an object")
    actual_keys = set(value)
    if actual_keys != expected_keys:
        missing = sorted(expected_keys - actual_keys)
        extra = sorted(actual_keys - expected_keys)
        raise ValueError(
            f"{name}: expected exactly {sorted(expected_keys)!r}; "
            f"missing={missing!r}, extra={extra!r}"
        )
    return {
        key: _to_unit_float(f"{name}.{key}", value[key])
        for key in sorted(expected_keys)
    }


def _validated_metrics_map(
    metrics_map: Mapping[str, Any] | None,
) -> dict[str, dict[str, float]]:
    """Resolve and strictly validate the checkpoint-promotion policy."""
    if metrics_map is not None and not isinstance(metrics_map, Mapping):
        raise ValueError("metrics map: expected a JSON object")
    override = dict(metrics_map or {})
    unknown = set(override) - _METRICS_MAP_KEYS
    if unknown:
        raise ValueError(f"metrics map: unknown keys {sorted(unknown)!r}")

    weights = _exact_unit_mapping(
        "vgs_weights",
        override.get("vgs_weights", DEFAULT_METRICS_MAP["vgs_weights"]),
        _WEIGHT_KEYS,
    )
    weight_sum = sum(weights.values())
    if not math.isclose(weight_sum, 1.0, rel_tol=0.0, abs_tol=1e-9):
        raise ValueError(
            f"vgs_weights: values must sum to 1.0, got {weight_sum!r}"
        )
    rules = _exact_unit_mapping(
        "regression_rules",
        override.get("regression_rules", DEFAULT_METRICS_MAP["regression_rules"]),
        _REGRESSION_RULE_KEYS,
    )
    return {"vgs_weights": weights, "regression_rules": rules}


def card_to_metrics(
    card: EvalCard,
    metrics_map: Mapping[str, Any] | None = None,
    *,
    cost_override: float | None = None,
    latency_override: float | None = None,
) -> tuple[ModelMetrics, MappingReport]:
    """Map an eval card onto ``ModelMetrics``.

    Returns the metrics plus a report of compatibility warnings. Raises
    ``ValueError`` on hard schema errors, including missing gate-critical
    invariance evidence.
    """
    m = _validated_metrics_map(metrics_map)
    weights = m["vgs_weights"]
    regression_rules = m["regression_rules"]

    warnings: list[str] = []

    model_id = card.get("model_id")
    if not isinstance(model_id, str) or not model_id.strip():
        raise ValueError("missing required gate field: model_id")

    # ---- VGS composite ----
    held_out = card.get("held_out_envs")
    if held_out is not None and not isinstance(held_out, dict):
        raise ValueError("held_out_envs: expected an object of unit-valued metrics")
    held_out_values = (
        [_to_unit_float(str(name), value) for name, value in held_out.items()]
        if held_out
        else []
    )
    mean_held_out_raw = card.get("mean_held_out_env_metric")
    if mean_held_out_raw is None:
        if not held_out_values:
            raise ValueError(
                "missing required gate field: mean_held_out_env_metric or held_out_envs"
            )
        mean_held_out = _mean(held_out_values)
    else:
        mean_held_out = _to_unit_float(
            "mean_held_out_env_metric", mean_held_out_raw
        )
        if held_out_values and not math.isclose(
            mean_held_out,
            _mean(held_out_values),
            rel_tol=0.0,
            abs_tol=1e-9,
        ):
            raise ValueError(
                "mean_held_out_env_metric disagrees with the recomputed "
                "mean of held_out_envs"
            )
    components = {
        "processbench_overall": _to_unit_float(
            "processbench_overall", _required(card, "processbench_overall")
        ),
        "mean_held_out_env_metric": mean_held_out,
        "bon_accuracy": _to_unit_float(
            "bon_accuracy", _required(card, "bon_accuracy")
        ),
    }

    vgs_value = sum(components[name] * weight for name, weight in weights.items())

    # ---- hack_risk from invariance violation rate ----
    inv = card.get("invariance_violation_rate")
    if inv is None:
        raise ValueError(
            "missing required gate field: invariance_violation_rate; "
            "shortcut risk is inconclusive until the invariance harness runs"
        )
    hack_risk = _to_unit_float("invariance_violation_rate", inv)

    # ---- calibration ← coverage ----
    calibration = _to_unit_float("coverage", _required(card, "coverage"))

    # ---- ood ← mean of held_out_envs ----
    ood = (
        _mean(held_out_values)
        if held_out_values
        else components["mean_held_out_env_metric"]
    )

    # ---- cost / latency ----
    cost = (
        cost_override
        if cost_override is not None
        else _to_nonnegative_float("cost", _required(card, "cost"))
    )
    latency = (
        latency_override
        if latency_override is not None
        else _to_nonnegative_float("latency", _required(card, "latency"))
    )
    cost = _to_nonnegative_float("cost", cost)
    latency = _to_nonnegative_float("latency", latency)

    # ---- regression flag ----
    pb = components["processbench_overall"]
    bon = components["bon_accuracy"]
    coverage_target = regression_rules["coverage_target"]
    coverage_tol = regression_rules["coverage_tol"]
    regression = bool(
        pb < regression_rules["processbench_min"]
        or abs(calibration - coverage_target) > coverage_tol
        or bon < 0.0  # placeholder — actual BoN-lift rule needs the OLD card too
    )

    return (
        ModelMetrics(
            vgs=vgs_value,
            hack_risk=hack_risk,
            calibration=calibration,
            ood=ood,
            cost=cost,
            latency=latency,
            regression=regression,
        ),
        MappingReport(warnings=tuple(warnings)),
    )


def evaluate_gate(
    old_card_path: str | Path,
    new_card_path: str | Path,
    tol: Tolerances,
    metrics_map_path: str | Path | None = None,
    *,
    cost_old: float | None = None,
    cost_new: float | None = None,
    latency_old: float | None = None,
    latency_new: float | None = None,
) -> tuple[GateDecision, ModelMetrics, ModelMetrics, list[str]]:
    """Load two cards, map to metrics, evaluate gate. Return (decision,
    old_metrics, new_metrics, warnings)."""

    metrics_map: Mapping[str, Any] | None = None
    if metrics_map_path is not None:
        with open(metrics_map_path, encoding="utf-8") as f:
            metrics_map = json.load(f)
    validated_metrics_map = _validated_metrics_map(metrics_map)

    old_card = EvalCard.load(old_card_path)
    new_card = EvalCard.load(new_card_path)

    old, report_old = card_to_metrics(
        old_card,
        validated_metrics_map,
        cost_override=cost_old,
        latency_override=latency_old,
    )
    new, report_new = card_to_metrics(
        new_card,
        validated_metrics_map,
        cost_override=cost_new,
        latency_override=latency_new,
    )

    warnings = [*report_old.warnings, *report_new.warnings]

    # Re-derive regression using the OLD bon_accuracy too (the rule
    # requires lift vs the previous checkpoint).
    rules = validated_metrics_map["regression_rules"]
    old_bon = _to_unit_float("bon_accuracy", _required(old_card, "bon_accuracy"))
    new_bon = _to_unit_float("bon_accuracy", _required(new_card, "bon_accuracy"))
    bon_lift = new_bon - old_bon
    if bon_lift < rules["bon_lift_min"]:
        new = ModelMetrics(
            vgs=new.vgs,
            hack_risk=new.hack_risk,
            calibration=new.calibration,
            ood=new.ood,
            cost=new.cost,
            latency=new.latency,
            regression=True,
        )

    decision = accept_update(tol, old, new)
    return decision, old, new, warnings
