"""Fail-closed validation at the public AssuranceCardV2 JSON boundary."""
from __future__ import annotations

import json
import math
from typing import Any

import pytest

from vlabs_sdk.schemas import AssuranceCardV2


def _card(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "card_version": "v2",
        "run_id": "run_test",
        "agent_id": None,
        "baseline_id": None,
        "candidate_id": None,
        "decision": "ACCEPT",
    }
    payload.update(overrides)
    return payload


@pytest.mark.parametrize("field", ["regression", "hf_public_safe"])
@pytest.mark.parametrize("invalid", [0, 1, "false", "true", None])
def test_boolean_fields_require_exact_json_booleans(field: str, invalid: Any) -> None:
    with pytest.raises((TypeError, ValueError), match=field):
        AssuranceCardV2.from_dict(_card(**{field: invalid}))


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        (field, invalid)
        for field in (
            "raw_vgs",
            "dcr",
            "public_score",
            "hidden_score",
            "ood_score",
            "hack_risk",
            "calibration",
        )
        for invalid in (True, math.nan, math.inf, -math.inf, -0.01, 1.01, "0.5")
    ],
)
def test_unit_scores_reject_booleans_nonfinite_and_out_of_range(
    field: str,
    invalid: Any,
) -> None:
    with pytest.raises((TypeError, ValueError), match=field):
        AssuranceCardV2.from_dict(_card(**{field: invalid}))


def test_clean_vgs_accepts_negative_finite_values_from_the_formal_formula() -> None:
    card = AssuranceCardV2.from_dict(_card(clean_vgs=-0.5))

    assert card.clean_vgs == -0.5


@pytest.mark.parametrize("invalid", [True, math.nan, math.inf, -math.inf, "-0.5"])
def test_clean_vgs_rejects_non_numbers_and_nonfinite_values(invalid: Any) -> None:
    with pytest.raises((TypeError, ValueError), match="clean_vgs"):
        AssuranceCardV2.from_dict(_card(clean_vgs=invalid))


@pytest.mark.parametrize("invalid", [True, math.nan, math.inf, -math.inf, -1.01, 1.01, "0"])
def test_generalization_gap_is_finite_and_bounded(invalid: Any) -> None:
    with pytest.raises((TypeError, ValueError), match="generalization_gap"):
        AssuranceCardV2.from_dict(_card(generalization_gap=invalid))


@pytest.mark.parametrize("field", ["cost", "latency"])
@pytest.mark.parametrize("invalid", [True, math.nan, math.inf, -math.inf, -0.01, "1"])
def test_cost_and_latency_are_finite_nonnegative_numbers(field: str, invalid: Any) -> None:
    with pytest.raises((TypeError, ValueError), match=field):
        AssuranceCardV2.from_dict(_card(**{field: invalid}))


@pytest.mark.parametrize(
    ("field", "invalid"),
    [
        ("decision", "accept"),
        ("decision", 1),
        ("redaction_status", "whatever"),
        ("redaction_status", 1),
        ("contamination_policy", "unknown"),
        ("contamination_policy", 1),
    ],
)
def test_enum_like_fields_accept_only_documented_exact_values(field: str, invalid: Any) -> None:
    with pytest.raises((TypeError, ValueError), match=field):
        AssuranceCardV2.from_dict(_card(**{field: invalid}))


def test_public_safe_flag_cannot_contradict_redaction_status() -> None:
    with pytest.raises(ValueError, match="hf_public_safe"):
        AssuranceCardV2.from_dict(_card(hf_public_safe=True, redaction_status="unredacted"))
    with pytest.raises(ValueError, match="redacted_public_safe"):
        AssuranceCardV2.from_dict(
            _card(hf_public_safe=False, redaction_status="redacted_public_safe")
        )

    assert AssuranceCardV2.from_dict(
        _card(hf_public_safe=True, redaction_status="redacted")
    ).hf_public_safe


@pytest.mark.parametrize(
    "invalid",
    ["one-reason", [1], [""], ["valid", None], ("tuple-is-not-json",)],
)
def test_from_dict_reject_reasons_requires_json_list_of_nonempty_strings(invalid: Any) -> None:
    with pytest.raises((TypeError, ValueError), match="reject_reasons"):
        AssuranceCardV2.from_dict(_card(reject_reasons=invalid))


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        [],
        {1: "non-string-key"},
        {"tuple": (1, 2)},
        {"set": {1, 2}},
        {"object": object()},
        {"nan": math.nan},
        {"nested": [1, {"infinity": math.inf}]},
    ],
)
def test_metadata_must_be_strict_finite_json_object(metadata: Any) -> None:
    with pytest.raises((TypeError, ValueError), match="metadata"):
        AssuranceCardV2.from_dict(_card(metadata=metadata))


def test_metadata_cycles_are_rejected_cleanly() -> None:
    metadata: dict[str, Any] = {}
    metadata["cycle"] = metadata

    with pytest.raises(ValueError, match="metadata.*cycle"):
        AssuranceCardV2.from_dict(_card(metadata=metadata))


def test_to_dict_revalidates_mutated_metadata_and_never_emits_nan() -> None:
    metadata: dict[str, Any] = {"safe": [True, None, 1, 1.5, "text"]}
    card = AssuranceCardV2.from_dict(_card(metadata=metadata))
    serialized = card.to_dict()

    assert json.loads(json.dumps(serialized, allow_nan=False)) == serialized

    card.metadata["late_nan"] = math.nan
    with pytest.raises(ValueError, match="metadata"):
        card.to_dict()


def test_legacy_shape_applies_same_boolean_and_reason_validation() -> None:
    legacy = {
        "card_version": "v2",
        "run_id": "legacy",
        "scores": {"public": 0.8, "hidden": 0.7, "ood": 0.6},
        "contamination": {"dcr": 0.1},
        "gate": {"outcome": "ACCEPT", "reasons": "not-a-list"},
        "regression": "false",
    }

    with pytest.raises((TypeError, ValueError), match="regression|reject_reasons"):
        AssuranceCardV2.from_dict(legacy)


def test_from_dict_requires_an_object() -> None:
    with pytest.raises(TypeError, match="data"):
        AssuranceCardV2.from_dict([])  # type: ignore[arg-type]
