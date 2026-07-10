"""Integration tests for ``vlabs-prm-eval gate``.

Exercises the Typer CLI end-to-end against eval-card JSON fixtures.
Each fixture is hand-crafted to trigger exactly one of the seven Lean
``AcceptUpdate`` rejection reasons (plus one accept fixture pair).

The mapping fixture → expected reason mirrors the field order in
``formal/VerifiableLabsFormal/SelfImprovementGate.lean``; if either the
Lean spec or the Python mirror in
``vlabs_sdk.formal_spec.gate`` changes, these tests will
catch drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner
from vlabs_sdk.formal_spec.gate import (
    REASON_CALIBRATION_DROPPED,
    REASON_COST_EXCEEDED,
    REASON_HACK_RISK_EXCEEDED,
    REASON_LATENCY_EXCEEDED,
    REASON_OOD_DROPPED,
    REASON_REGRESSION_FLAG_SET,
    REASON_VGS_GAIN_BELOW_TAU,
    Tolerances,
)

from vlabs_prm_eval.cli import app
from vlabs_prm_eval.gate import (
    DEFAULT_METRICS_MAP,
    EvalCard,
    card_to_metrics,
    evaluate_gate,
)

FIXTURES = Path(__file__).parent / "fixtures"
OLD = FIXTURES / "card_old.json"


def _runner() -> CliRunner:
    return CliRunner()


# =====================================================================
# Accept path
# =====================================================================
def test_gate_cli_accept():
    """Healthy candidate clears all seven conditions → exit 0, ACCEPT header."""
    result = _runner().invoke(
        app,
        ["gate", "--old", str(OLD), "--new", str(FIXTURES / "card_new_accept.json")],
    )
    assert result.exit_code == 0, result.stdout
    assert "ACCEPT" in result.stdout
    assert "REJECT" not in result.stdout
    assert "Reasons:" not in result.stdout


# =====================================================================
# One reject per AcceptUpdate condition
# =====================================================================
@pytest.mark.parametrize(
    "fixture, expected_reason",
    [
        ("card_reject_vgs.json",        REASON_VGS_GAIN_BELOW_TAU),
        ("card_reject_hack.json",       REASON_HACK_RISK_EXCEEDED),
        ("card_reject_calib.json",      REASON_CALIBRATION_DROPPED),
        ("card_reject_ood.json",        REASON_OOD_DROPPED),
        ("card_reject_cost.json",       REASON_COST_EXCEEDED),
        ("card_reject_latency.json",    REASON_LATENCY_EXCEEDED),
        ("card_reject_regression.json", REASON_REGRESSION_FLAG_SET),
    ],
)
def test_gate_cli_rejects(fixture: str, expected_reason: str):
    """Each fixture triggers its named Lean ``AcceptUpdate`` reason."""
    result = _runner().invoke(
        app,
        ["gate", "--old", str(OLD), "--new", str(FIXTURES / fixture)],
    )
    assert result.exit_code == 1, (fixture, result.stdout)
    assert "REJECT" in result.stdout
    assert expected_reason in result.stdout, (
        f"expected reason {expected_reason!r} not surfaced for {fixture}; "
        f"stdout was:\n{result.stdout}"
    )


# =====================================================================
# Schema bridge — eval-card → ModelMetrics
# =====================================================================
def test_card_to_metrics_default_mapping():
    """Spot-check the documented default weights/aggregations."""
    card = EvalCard.load(FIXTURES / "card_old.json")
    metrics, report = card_to_metrics(card)
    # vgs = 0.4*0.75 + 0.3*0.70 + 0.3*0.65 = 0.705
    assert metrics.vgs == pytest.approx(0.705, abs=1e-9)
    assert metrics.hack_risk == pytest.approx(0.10, abs=1e-9)
    assert metrics.calibration == pytest.approx(0.90, abs=1e-9)
    assert metrics.ood == pytest.approx(0.70, abs=1e-9)
    assert metrics.cost == 1.0 and metrics.latency == 1.0
    assert metrics.regression is False
    assert report.warnings == ()


def test_card_to_metrics_rejects_asserted_held_out_mean_that_disagrees_with_rows():
    import json

    raw = json.loads((FIXTURES / "card_old.json").read_text())
    assert raw["held_out_envs"]
    raw["mean_held_out_env_metric"] = 0.01

    with pytest.raises(ValueError, match="mean_held_out_env_metric.*held_out_envs"):
        card_to_metrics(EvalCard(raw=raw))


def test_card_to_metrics_missing_invariance_is_inconclusive():
    """Missing shortcut evidence must never be converted into ideal hack risk."""
    import json

    raw = json.loads((FIXTURES / "card_old.json").read_text())
    raw.pop("invariance_violation_rate")
    with pytest.raises(ValueError, match="missing required gate field.*invariance"):
        card_to_metrics(EvalCard(raw=raw))


def test_gate_cli_missing_invariance_exits_inconclusive(tmp_path):
    import json

    raw = json.loads((FIXTURES / "card_new_accept.json").read_text())
    raw.pop("invariance_violation_rate")
    card = tmp_path / "missing-invariance.json"
    card.write_text(json.dumps(raw))

    result = _runner().invoke(app, ["gate", "--old", str(OLD), "--new", str(card)])
    assert result.exit_code == 2
    assert "INCONCLUSIVE" in result.stdout
    assert "invariance_violation_rate" in result.stdout
    assert "ACCEPT" not in result.stdout


@pytest.mark.parametrize(
    ("missing", "also_remove"),
    [
        ("processbench_overall", None),
        ("bon_accuracy", None),
        ("coverage", None),
        ("cost", None),
        ("latency", None),
        ("mean_held_out_env_metric", "held_out_envs"),
    ],
)
def test_gate_cli_missing_gate_dimension_is_inconclusive(
    tmp_path, missing, also_remove
):
    import json

    raw = json.loads((FIXTURES / "card_new_accept.json").read_text())
    raw.pop(missing)
    if also_remove is not None:
        raw.pop(also_remove, None)
    card = tmp_path / f"missing-{missing}.json"
    card.write_text(json.dumps(raw))

    result = _runner().invoke(app, ["gate", "--old", str(OLD), "--new", str(card)])
    assert result.exit_code == 2
    assert "INCONCLUSIVE" in result.stdout
    assert "ACCEPT" not in result.stdout


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("processbench_overall", 1.01),
        ("bon_accuracy", -0.01),
        ("coverage", float("nan")),
        ("invariance_violation_rate", float("inf")),
    ],
)
def test_gate_unit_metrics_reject_out_of_range_or_nonfinite(field, value):
    import json

    raw = json.loads((FIXTURES / "card_old.json").read_text())
    raw[field] = value
    with pytest.raises(ValueError, match=field):
        card_to_metrics(EvalCard(raw=raw))


def test_evaluate_gate_returns_decision_old_new_warnings():
    """Direct API surface used by the CLI."""
    decision, old_m, new_m, warnings = evaluate_gate(
        old_card_path=OLD,
        new_card_path=FIXTURES / "card_new_accept.json",
        tol=Tolerances(),
    )
    assert decision.accepted is True
    assert decision.reasons == ()
    assert new_m.vgs > old_m.vgs
    assert warnings == []


# =====================================================================
# --metrics-map override
# =====================================================================
def test_metrics_map_override_changes_weights(tmp_path):
    """A custom ``vgs_weights`` map flips an accept fixture into a reject
    by making the BoN component dominate (where the new card improves
    less than tau under the new weighting)."""
    import json

    # Re-weight so processbench_overall is *almost* the entire VGS and
    # the candidate's tiny processbench gain (+0.05) still clears tau,
    # but tighten tau so the gain falls below it.
    override = {
        "vgs_weights": {
            "processbench_overall": 0.10,
            "mean_held_out_env_metric": 0.10,
            "bon_accuracy": 0.80,
        },
        "regression_rules": DEFAULT_METRICS_MAP["regression_rules"],
    }
    map_path = tmp_path / "map.json"
    map_path.write_text(json.dumps(override))

    # bon_lift = 0.72 - 0.65 = 0.07; weighted gain ≈ 0.056 + 0.005 + 0.005 = 0.066
    # That still exceeds tau=0.01. So bump tau above the achievable gain
    # to force the reject.
    result = _runner().invoke(
        app,
        [
            "gate",
            "--old", str(OLD),
            "--new", str(FIXTURES / "card_new_accept.json"),
            "--metrics-map", str(map_path),
            "--tau", "0.10",
        ],
    )
    assert result.exit_code == 1
    assert REASON_VGS_GAIN_BELOW_TAU in result.stdout


@pytest.mark.parametrize(
    "override",
    [
        {"vgs_weights": {"processbench_overall": -0.1,
                         "mean_held_out_env_metric": 0.3, "bon_accuracy": 0.8}},
        {"vgs_weights": {"processbench_overall": float("nan"),
                         "mean_held_out_env_metric": 0.3, "bon_accuracy": 0.7}},
        {"vgs_weights": {"processbench_overall": 0.5,
                         "mean_held_out_env_metric": 0.5}},
        {"vgs_weights": {"processbench_overall": 0.4,
                         "mean_held_out_env_metric": 0.3, "bon_accuracy": 0.2}},
        {"vgs_weights": {"processbench_overall": 0.4,
                         "mean_held_out_env_metric": 0.3, "bon_accuracy": 0.3,
                         "unknown_component": 0.0}},
        {"regression_rules": {"processbench_min": -0.1, "bon_lift_min": 0.05,
                              "coverage_target": 0.9, "coverage_tol": 0.05}},
        {"regression_rules": {"processbench_min": 0.6,
                              "bon_lift_min": float("inf"),
                              "coverage_target": 0.9, "coverage_tol": 0.05}},
        {"regression_rules": {"processbench_min": 0.6, "bon_lift_min": 0.05,
                              "coverage_target": 0.9}},
        {"regression_rules": {"processbench_min": 0.6, "bon_lift_min": 0.05,
                              "coverage_target": 1.1, "coverage_tol": 0.05}},
        {"regression_rules": {"processbench_min": 0.6, "bon_lift_min": 0.05,
                              "coverage_target": 0.9, "coverage_tol": 0.05,
                              "typo_rule": 0.0}},
        {"vgs_weight": DEFAULT_METRICS_MAP["vgs_weights"]},
    ],
)
def test_metrics_map_policy_rejects_malformed_overrides(override):
    with pytest.raises(ValueError, match="metrics map|vgs_weights|regression_rules"):
        card_to_metrics(EvalCard.load(OLD), override)


def test_metrics_map_cli_malformed_policy_is_inconclusive(tmp_path):
    import json

    map_path = tmp_path / "bad-map.json"
    map_path.write_text(
        json.dumps(
            {
                "vgs_weights": {
                    "processbench_overall": -1.0,
                    "mean_held_out_env_metric": 1.0,
                    "bon_accuracy": 1.0,
                }
            }
        )
    )
    result = _runner().invoke(
        app,
        [
            "gate",
            "--old", str(OLD),
            "--new", str(FIXTURES / "card_new_accept.json"),
            "--metrics-map", str(map_path),
        ],
    )
    assert result.exit_code == 2
    assert "INCONCLUSIVE" in result.stdout
    assert "ACCEPT" not in result.stdout


# =====================================================================
# Exit-code contract (sanity ladder for CI wiring)
# =====================================================================
def test_gate_exit_zero_on_accept():
    result = _runner().invoke(
        app,
        ["gate", "--old", str(OLD), "--new", str(FIXTURES / "card_new_accept.json")],
    )
    assert result.exit_code == 0


def test_gate_exit_one_on_reject():
    result = _runner().invoke(
        app,
        ["gate", "--old", str(OLD), "--new", str(FIXTURES / "card_reject_vgs.json")],
    )
    assert result.exit_code == 1
