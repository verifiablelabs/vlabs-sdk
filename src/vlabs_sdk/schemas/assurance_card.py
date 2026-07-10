"""Assurance Card v2 schema + the vetted formal-claim text (SDK-safe).

The card is the human- and machine-readable verdict of a run. ``FORMAL_CLAIM``
is the ONLY approved wording about formal verification; every card, doc, and
export reuses this exact string so the honesty rule cannot drift. It must
never be reworded into "formally verified API/system/product/code".
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

# The single source of truth for the formal-verification claim (honesty rule).
FORMAL_CLAIM = (
    "Selected mathematical properties behind the contamination-resistant "
    "promotion gate are machine-verified in Lean 4. A hand-maintained Python "
    "mirror has property tests derived from selected definitions; no mechanized "
    "code-to-proof parity is claimed."
)

# Phrases that must never appear anywhere (asserted by the forbidden-claims
# grep in T10). Exposed here so tests can import the canonical list.
FORBIDDEN_CLAIMS = (
    "formally verified system",  # never allowed
    "formally verified api",  # never allowed
    "formally verified product",  # never allowed
    "formally verified code",  # never allowed
    "formally verified service",  # never allowed
    "we prove the model generalizes",
    "we eliminate contamination",
    "guarantee general intelligence",
    "prove agi safety",
)


class GateDecisionLabel(StrEnum):
    ACCEPT = "ACCEPT"
    REJECT = "REJECT"
    LIMITED_ROLLOUT = "LIMITED_ROLLOUT"


class ContaminationPolicyLabel(StrEnum):
    GENERATED_AFTER_FREEZE = "generated_after_freeze"


class RedactionStatusLabel(StrEnum):
    UNREDACTED = "unredacted"
    REDACTED = "redacted"
    REDACTED_PUBLIC_SAFE = "redacted_public_safe"
    PII_PENDING = "pii_pending"


_UNIT_FIELDS = (
    "raw_vgs",
    "dcr",
    "public_score",
    "hidden_score",
    "ood_score",
    "hack_risk",
    "calibration",
)
_MAX_METADATA_DEPTH = 64


def _require_nonempty_string(name: str, value: object) -> None:
    if not isinstance(value, str) or not value.strip():
        raise TypeError(f"{name} must be a non-empty string")


def _require_optional_string(name: str, value: object) -> None:
    if value is not None:
        _require_nonempty_string(name, value)


def _require_exact_bool(name: str, value: object) -> None:
    if type(value) is not bool:
        raise TypeError(f"{name} must be a boolean")


def _require_optional_number(name: str, value: object) -> float | None:
    if value is None:
        return None
    if type(value) not in (int, float):
        raise TypeError(f"{name} must be a JSON number")
    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be finite")
    return numeric


def _require_optional_unit(name: str, value: object) -> None:
    numeric = _require_optional_number(name, value)
    if numeric is not None and not 0.0 <= numeric <= 1.0:
        raise ValueError(f"{name} must be in [0, 1]")


def _require_optional_bounded(
    name: str,
    value: object,
    *,
    minimum: float,
    maximum: float,
) -> None:
    numeric = _require_optional_number(name, value)
    if numeric is not None and not minimum <= numeric <= maximum:
        raise ValueError(f"{name} must be in [{minimum:g}, {maximum:g}]")


def _require_optional_nonnegative(name: str, value: object) -> None:
    numeric = _require_optional_number(name, value)
    if numeric is not None and numeric < 0.0:
        raise ValueError(f"{name} must be >= 0")


def _require_reject_reasons_tuple(value: object) -> None:
    if type(value) is not tuple:
        raise TypeError("reject_reasons must be a tuple of non-empty strings")
    if any(not isinstance(reason, str) or not reason.strip() for reason in value):
        raise TypeError("reject_reasons must contain only non-empty strings")


def _json_reasons(value: object) -> tuple[str, ...]:
    if type(value) is not list:
        raise TypeError("reject_reasons must be a JSON list of non-empty strings")
    if any(not isinstance(reason, str) or not reason.strip() for reason in value):
        raise TypeError("reject_reasons must contain only non-empty strings")
    return tuple(value)


def _validate_json_value(
    value: object,
    *,
    path: str,
    active: set[int],
    depth: int,
) -> None:
    if depth > _MAX_METADATA_DEPTH:
        raise ValueError(f"{path} exceeds maximum metadata nesting depth")
    if value is None or type(value) in (str, bool, int):
        return
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError(f"{path} must not contain NaN or Infinity")
        return
    if type(value) not in (dict, list):
        raise TypeError(f"{path} contains a non-JSON value of type {type(value).__name__}")

    identity = id(value)
    if identity in active:
        raise ValueError(f"{path} contains a cycle")
    active.add(identity)
    try:
        if type(value) is list:
            for index, item in enumerate(value):
                _validate_json_value(
                    item,
                    path=f"{path}[{index}]",
                    active=active,
                    depth=depth + 1,
                )
            return
        for key, item in value.items():
            if type(key) is not str:
                raise TypeError(f"{path} keys must be strings")
            _validate_json_value(
                item,
                path=f"{path}.{key}",
                active=active,
                depth=depth + 1,
            )
    finally:
        active.remove(identity)


def _validate_metadata(value: object) -> None:
    if type(value) is not dict:
        raise TypeError("metadata must be a JSON object")
    _validate_json_value(value, path="metadata", active=set(), depth=0)


def _legacy_object(raw: dict[str, Any], key: str) -> dict[str, Any]:
    value = raw.get(key, {})
    if type(value) is not dict:
        raise TypeError(f"{key} must be a JSON object")
    return value


@dataclass(frozen=True)
class AssuranceCardV2:
    """Run verdict. Carries scores, transfer, gate decision, and the formal
    scope — plus redaction/export-safety flags so it is never published with
    private content by accident."""

    card_version: str
    run_id: str
    agent_id: str | None
    baseline_id: str | None
    candidate_id: str | None
    decision: str
    raw_vgs: float | None = None
    dcr: float | None = None
    clean_vgs: float | None = None
    public_score: float | None = None
    hidden_score: float | None = None
    ood_score: float | None = None
    generalization_gap: float | None = None
    hack_risk: float | None = None
    calibration: float | None = None
    cost: float | None = None
    latency: float | None = None
    regression: bool = False
    reject_reasons: tuple[str, ...] = ()
    formal_claim: str = FORMAL_CLAIM
    formal_scope: str = FORMAL_CLAIM
    contamination_policy: str = "generated_after_freeze"
    redaction_status: str = "unredacted"
    hf_public_safe: bool = False
    wandb_run_url: str | None = None
    hf_dataset_url: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_nonempty_string("card_version", self.card_version)
        if self.card_version != "v2":
            raise ValueError("card_version must be v2")
        _require_nonempty_string("run_id", self.run_id)
        for name in ("agent_id", "baseline_id", "candidate_id"):
            _require_optional_string(name, getattr(self, name))
        _require_nonempty_string("decision", self.decision)
        if self.decision not in {d.value for d in GateDecisionLabel}:
            raise ValueError("decision must be ACCEPT, REJECT, or LIMITED_ROLLOUT")
        for name in _UNIT_FIELDS:
            _require_optional_unit(name, getattr(self, name))
        # The canonical formal formula is
        # raw_vgs * (1 - dcr) - beta * dcr.  With beta >= 0 it can be
        # negative (and equals -beta at full contamination), so clean_vgs is
        # any finite JSON number rather than a unit-interval score.
        _require_optional_number("clean_vgs", self.clean_vgs)
        _require_optional_bounded(
            "generalization_gap",
            self.generalization_gap,
            minimum=-1.0,
            maximum=1.0,
        )
        _require_optional_nonnegative("cost", self.cost)
        _require_optional_nonnegative("latency", self.latency)
        _require_exact_bool("regression", self.regression)
        _require_exact_bool("hf_public_safe", self.hf_public_safe)
        _require_reject_reasons_tuple(self.reject_reasons)
        # Honesty guard: the formal claim must be the vetted text verbatim.
        _require_nonempty_string("formal_claim", self.formal_claim)
        _require_nonempty_string("formal_scope", self.formal_scope)
        if self.formal_claim != FORMAL_CLAIM:
            raise ValueError("formal_claim must be the vetted FORMAL_CLAIM text")
        if self.formal_scope != FORMAL_CLAIM:
            raise ValueError("formal_scope must be the vetted FORMAL_CLAIM text")
        _require_nonempty_string("contamination_policy", self.contamination_policy)
        if self.contamination_policy not in {p.value for p in ContaminationPolicyLabel}:
            raise ValueError("contamination_policy must be generated_after_freeze")
        _require_nonempty_string("redaction_status", self.redaction_status)
        if self.redaction_status not in {s.value for s in RedactionStatusLabel}:
            raise ValueError(
                "redaction_status must be unredacted, redacted, "
                "redacted_public_safe, or pii_pending"
            )
        if self.hf_public_safe and self.redaction_status not in {
            RedactionStatusLabel.REDACTED.value,
            RedactionStatusLabel.REDACTED_PUBLIC_SAFE.value,
        }:
            raise ValueError("hf_public_safe requires a redacted redaction_status")
        if (
            self.redaction_status == RedactionStatusLabel.REDACTED_PUBLIC_SAFE.value
            and not self.hf_public_safe
        ):
            raise ValueError("redacted_public_safe requires hf_public_safe=true")
        _require_optional_string("wandb_run_url", self.wandb_run_url)
        _require_optional_string("hf_dataset_url", self.hf_dataset_url)
        _validate_metadata(self.metadata)

    def to_dict(self) -> dict[str, Any]:
        # ``frozen=True`` does not recursively freeze the metadata dict. Revalidate
        # at every export so a late mutation can never emit NaN or a non-JSON object.
        _validate_metadata(self.metadata)
        d = asdict(self)
        d["reject_reasons"] = list(self.reject_reasons)
        # Python's JSON encoder otherwise emits non-standard NaN/Infinity tokens.
        json.dumps(d, allow_nan=False)
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AssuranceCardV2:
        """Load canonical v2 cards and the pre-canonical public nested shape.

        Early public examples used ``scores``/``contamination``/``gate``
        objects while already labelling themselves v2. This compatibility
        reader keeps those artifacts usable; :meth:`to_dict` always emits the
        canonical flat schema.
        """
        if type(data) is not dict:
            raise TypeError("data must be a JSON object")
        raw = dict(data)
        legacy = any(key in raw for key in ("scores", "contamination", "gate"))
        if not legacy:
            comment = raw.pop("_comment", None)
            if comment is not None:
                _require_nonempty_string("_comment", comment)
            if "metadata" in raw and type(raw["metadata"]) is not dict:
                raise TypeError("metadata must be a JSON object")
            metadata = dict(raw.get("metadata", {}))
            if comment is not None:
                metadata["comment"] = comment
            raw["metadata"] = metadata
            if "reject_reasons" in raw:
                raw["reject_reasons"] = _json_reasons(raw["reject_reasons"])
            return cls(**raw)

        scores = _legacy_object(raw, "scores")
        contamination = _legacy_object(raw, "contamination")
        gate = _legacy_object(raw, "gate")
        clean = raw.get("clean_vgs")
        candidate_clean = clean.get("candidate") if isinstance(clean, dict) else clean
        if "metadata" in raw and type(raw["metadata"]) is not dict:
            raise TypeError("metadata must be a JSON object")
        metadata = dict(raw.get("metadata", {}))
        comment = raw.get("_comment")
        if comment is not None:
            _require_nonempty_string("_comment", comment)
        org = raw.get("org")
        if org is not None:
            _require_nonempty_string("org", org)
        adversarial_score = scores.get("adversarial")
        _require_optional_unit("scores.adversarial", adversarial_score)
        metadata.update(
            {
                "legacy_v2_shape": True,
                "comment": comment,
                "org": org,
                "adversarial_score": adversarial_score,
            }
        )
        if isinstance(clean, dict):
            baseline_clean_vgs = clean.get("baseline")
            _require_optional_number("clean_vgs.baseline", baseline_clean_vgs)
            metadata["baseline_clean_vgs"] = baseline_clean_vgs
        reasons = raw.get("reject_reasons", gate.get("reasons", []))
        return cls(
            card_version=raw.get("card_version", "v2"),
            run_id=raw["run_id"],
            agent_id=raw.get("agent_id", raw.get("agent")),
            baseline_id=raw.get("baseline_id"),
            candidate_id=raw.get("candidate_id"),
            decision=raw.get("decision", gate.get("outcome")),
            raw_vgs=raw.get("raw_vgs"),
            dcr=raw.get("dcr", contamination.get("dcr")),
            clean_vgs=candidate_clean,
            public_score=raw.get("public_score", scores.get("public")),
            hidden_score=raw.get("hidden_score", scores.get("hidden")),
            ood_score=raw.get("ood_score", scores.get("ood")),
            generalization_gap=raw.get("generalization_gap"),
            hack_risk=raw.get("hack_risk"),
            calibration=raw.get("calibration"),
            cost=raw.get("cost"),
            latency=raw.get("latency"),
            regression=raw.get("regression", False),
            reject_reasons=_json_reasons(reasons),
            formal_claim=raw.get("formal_claim", FORMAL_CLAIM),
            formal_scope=raw.get("formal_scope", FORMAL_CLAIM),
            contamination_policy=raw.get("contamination_policy", "generated_after_freeze"),
            redaction_status=raw.get("redaction_status", "unredacted"),
            hf_public_safe=raw.get("hf_public_safe", False),
            wandb_run_url=raw.get("wandb_run_url"),
            hf_dataset_url=raw.get("hf_dataset_url"),
            metadata=metadata,
        )
