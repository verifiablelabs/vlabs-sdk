"""Fail-closed parity tests for the generated-after-freeze helper."""

import pytest

from vlabs_sdk.formal_spec.generated_after_freeze import (
    EvalScenario,
    Model,
    generated_after_freeze_not_in_training,
)


def test_explicit_training_membership_overrides_timestamp_inference() -> None:
    model = Model(training_cutoff=100.0, freeze_time=100.0)
    scenario = EvalScenario(generated_at=150.0)

    assert generated_after_freeze_not_in_training(model, scenario, True) is False
    assert generated_after_freeze_not_in_training(model, scenario, False) is True


@pytest.mark.parametrize("value", [0, 1, "false", None])
def test_training_membership_requires_an_exact_boolean(value: object) -> None:
    model = Model(training_cutoff=100.0, freeze_time=100.0)
    scenario = EvalScenario(generated_at=150.0)

    with pytest.raises(TypeError, match="in_training_data must be a bool"):
        generated_after_freeze_not_in_training(model, scenario, value)  # type: ignore[arg-type]
