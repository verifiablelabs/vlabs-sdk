"""Integration tests for ``vlabs-prm-eval clean-gate``.

Exercises the Typer CLI end-to-end against eval-card JSON fixtures. Each reject
fixture is hand-crafted to trigger exactly one of the eight Lean
``CleanAcceptUpdate`` rejection reasons (plus one accept fixture pair and one
fixture that exercises the missing-field warnings path).

The mapping fixture → expected reason mirrors the field order in
``formal/VerifiableLabsFormal/CleanPromotionGate.lean``; if either the Lean spec
or the Python mirror in ``vlabs_sdk.formal_spec.clean_promotion_gate``
changes, these tests catch drift.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner
from vlabs_sdk.formal_spec.clean_promotion_gate import (
    REASON_CALIBRATION_REGRESSED,
    REASON_CLEAN_VGS_NOT_IMPROVED,
    REASON_COST_INCREASED,
    REASON_DCR_INCREASED,
    REASON_HACK_RISK_INCREASED,
    REASON_LATENCY_INCREASED,
    REASON_OOD_REGRESSED,
    REASON_REGRESSION_FLAGGED,
    CleanTolerances,
)

from vlabs_prm_eval.clean_gate import (
    CleanEvalCard,
    card_to_clean_metrics,
    evaluate_clean_gate,
)
from vlabs_prm_eval.cli import app

FIXTURES = Path(__file__).parent / "fixtures" / "clean"
OLD = FIXTURES / "clean_old.json"


def _runner() -> CliRunner:
    return CliRunner()


# =====================================================================
# Accept path
# =====================================================================
def test_clean_gate_cli_accept():
    """Healthy candidate clears all eight conditions → exit 0, ACCEPT header."""
    result = _runner().invoke(
        app,
        ["clean-gate", "--old", str(OLD), "--new", str(FIXTURES / "clean_new_accept.json")],
    )
    assert result.exit_code == 0, result.stdout
    assert "ACCEPT" in result.stdout
    assert "REJECT" not in result.stdout
    assert "Reasons:" not in result.stdout


def test_clean_gate_does_not_remove_gate_command():
    """The original ``gate`` command must still exist alongside ``clean-gate``."""
    result = _runner().invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "clean-gate" in result.stdout
    assert "gate" in result.stdout


# =====================================================================
# One reject per CleanAcceptUpdate condition
# =====================================================================
@pytest.mark.parametrize(
    "fixture, expected_reason",
    [
        ("clean_reject_clean_vgs.json",  REASON_CLEAN_VGS_NOT_IMPROVED),
        ("clean_reject_hack.json",       REASON_HACK_RISK_INCREASED),
        ("clean_reject_calib.json",      REASON_CALIBRATION_REGRESSED),
        ("clean_reject_ood.json",        REASON_OOD_REGRESSED),
        ("clean_reject_dcr.json",        REASON_DCR_INCREASED),
        ("clean_reject_cost.json",       REASON_COST_INCREASED),
        ("clean_reject_latency.json",    REASON_LATENCY_INCREASED),
        ("clean_reject_regression.json", REASON_REGRESSION_FLAGGED),
    ],
)
def test_clean_gate_cli_rejects(fixture: str, expected_reason: str):
    """Each fixture triggers its named Lean ``CleanAcceptUpdate`` reason."""
    result = _runner().invoke(
        app,
        ["clean-gate", "--old", str(OLD), "--new", str(FIXTURES / fixture)],
    )
    assert result.exit_code == 1, (fixture, result.stdout)
    assert "REJECT" in result.stdout
    assert expected_reason in result.stdout, (
        f"expected reason {expected_reason!r} not surfaced for {fixture}; "
        f"stdout was:\n{result.stdout}"
    )


def test_each_reject_fixture_triggers_exactly_one_reason():
    """Direct API: each reject fixture yields exactly one reason."""
    tol = CleanTolerances()
    cases = {
        "clean_reject_clean_vgs.json":  REASON_CLEAN_VGS_NOT_IMPROVED,
        "clean_reject_hack.json":       REASON_HACK_RISK_INCREASED,
        "clean_reject_calib.json":      REASON_CALIBRATION_REGRESSED,
        "clean_reject_ood.json":        REASON_OOD_REGRESSED,
        "clean_reject_dcr.json":        REASON_DCR_INCREASED,
        "clean_reject_cost.json":       REASON_COST_INCREASED,
        "clean_reject_latency.json":    REASON_LATENCY_INCREASED,
        "clean_reject_regression.json": REASON_REGRESSION_FLAGGED,
    }
    for fixture, reason in cases.items():
        decision, _, _, _ = evaluate_clean_gate(
            OLD, FIXTURES / fixture, tol, beta=0.5
        )
        assert decision.accepted is False, fixture
        assert decision.reasons == (reason,), (fixture, decision.reasons)


# =====================================================================
# Fail-closed schema bridge
# =====================================================================
def test_clean_gate_rejects_missing_safety_metrics():
    """A promotion gate must not replace missing safety evidence with ideal values."""
    with pytest.raises(ValueError, match="missing required clean-gate fields"):
        evaluate_clean_gate(
            OLD, FIXTURES / "clean_new_warnings.json", CleanTolerances(), beta=0.5
        )


def test_clean_gate_cli_fails_on_missing_safety_metrics():
    result = _runner().invoke(
        app,
        ["clean-gate", "--old", str(OLD), "--new", str(FIXTURES / "clean_new_warnings.json")],
    )
    assert result.exit_code == 2
    assert "INCONCLUSIVE" in result.stdout
    assert "missing required clean-gate fields" in result.stdout
    assert "ACCEPT" not in result.stdout


def test_card_to_clean_metrics_recomputes_supplied_clean_vgs():
    """The formal formula, not a caller-controlled derived field, is authoritative."""
    card = CleanEvalCard(
        {
            "vgs": 0.8,
            "dcr": 0.1,
            "clean_vgs": 999.0,
            "ood_score": 0.7,
            "hack_risk": 0.1,
            "calibration": 0.9,
            "cost": 1.0,
            "latency": 1.0,
        }
    )
    metrics, report = card_to_clean_metrics(card, beta=0.5)
    assert metrics.clean_vgs == pytest.approx(0.67, abs=1e-9)
    assert any("ignored" in warning and "clean_vgs" in warning for warning in report.warnings)


@pytest.mark.parametrize(
    "aliases",
    [
        {"vgs": 0.8, "composite": 0.7},
        {"contamination_risk": 0.1, "dcr": 0.2},
    ],
)
def test_clean_gate_rejects_conflicting_alias_values(aliases):
    raw = {
        "vgs": 0.8,
        "dcr": 0.1,
        "ood_score": 0.7,
        "hack_risk": 0.1,
        "calibration": 0.9,
        "cost": 1.0,
        "latency": 1.0,
        **aliases,
    }

    with pytest.raises(ValueError, match="conflicting aliases"):
        card_to_clean_metrics(CleanEvalCard(raw), beta=0.5)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("vgs", -0.01),
        ("vgs", 1.01),
        ("dcr", -0.01),
        ("dcr", 1.01),
        ("ood_score", 1.01),
        ("hack_risk", -0.01),
        ("calibration", 1.01),
    ],
)
def test_card_to_clean_metrics_enforces_documented_unit_ranges(field, value):
    raw = {
        "vgs": 0.8,
        "dcr": 0.1,
        "ood_score": 0.7,
        "hack_risk": 0.1,
        "calibration": 0.9,
        "cost": 1.0,
        "latency": 1.0,
    }
    raw[field] = value
    with pytest.raises(ValueError, match=r"must be in \[0, 1\]"):
        card_to_clean_metrics(CleanEvalCard(raw), beta=0.5)


@pytest.mark.parametrize(
    "override",
    [
        {"unknown_policy_key": []},
        {"raw_vgs_keys": "vgs"},
        {"raw_vgs_keys": []},
        {"raw_vgs_keys": ["vgs", "vgs"]},
        {"dcr_keys": ["dcr", 7]},
        {"dcr_default": float("nan")},
        {"cost_default": -1.0},
    ],
)
def test_clean_metrics_map_rejects_unknown_or_ill_typed_policy(override):
    with pytest.raises(ValueError, match="metrics map|_keys|_default"):
        card_to_clean_metrics(CleanEvalCard.load(OLD), beta=0.5, metrics_map=override)


def test_clean_metrics_map_cli_malformed_policy_is_inconclusive(tmp_path):
    import json

    map_path = tmp_path / "bad-clean-map.json"
    map_path.write_text(json.dumps({"hack_risk_keys": "hack_risk"}))
    result = _runner().invoke(
        app,
        [
            "clean-gate",
            "--old", str(OLD),
            "--new", str(FIXTURES / "clean_new_accept.json"),
            "--metrics-map", str(map_path),
        ],
    )
    assert result.exit_code == 2
    assert "INCONCLUSIVE" in result.stdout
    assert "ACCEPT" not in result.stdout


# =====================================================================
# Exit-code contract
# =====================================================================
def test_clean_gate_exit_zero_on_accept():
    result = _runner().invoke(
        app,
        ["clean-gate", "--old", str(OLD), "--new", str(FIXTURES / "clean_new_accept.json")],
    )
    assert result.exit_code == 0


def test_clean_gate_exit_one_on_reject():
    result = _runner().invoke(
        app,
        ["clean-gate", "--old", str(OLD), "--new", str(FIXTURES / "clean_reject_dcr.json")],
    )
    assert result.exit_code == 1
