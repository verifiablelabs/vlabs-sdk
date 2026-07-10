"""Strict runtime type checks for contamination split policy."""

import pytest

from vlabs_sdk.schemas.splits import Split, is_trainable, validate_split_policy


def test_raw_hidden_eval_string_cannot_bypass_enum_identity_checks() -> None:
    with pytest.raises(TypeError, match="split must be a Split"):
        is_trainable("hidden_eval", True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="split must be a Split"):
        validate_split_policy(  # type: ignore[arg-type]
            "hidden_eval", train_allowed=True, public_release_allowed=True
        )


@pytest.mark.parametrize("flag", [0, 1, "false", None])
def test_policy_flags_require_exact_booleans(flag: object) -> None:
    with pytest.raises(TypeError, match="train_allowed must be a bool"):
        is_trainable(Split.TRAIN, flag)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="train_allowed must be a bool"):
        validate_split_policy(  # type: ignore[arg-type]
            Split.TRAIN, train_allowed=flag, public_release_allowed=False
        )
    with pytest.raises(TypeError, match="public_release_allowed must be a bool"):
        validate_split_policy(  # type: ignore[arg-type]
            Split.TRAIN, train_allowed=False, public_release_allowed=flag
        )
