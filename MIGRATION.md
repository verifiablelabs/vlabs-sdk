# Migrating from `verifiable-labs-envs` to `vlabs-sdk`

The SDK-contract surface of the legacy `verifiable-labs-envs` package now
ships as **`vlabs-sdk`** with its own import namespace. There is no
compatibility alias — the two packages are deliberately installable side
by side without conflict.

| | legacy | new |
|---|---|---|
| pip package | `verifiable-labs-envs` | `vlabs-sdk` |
| import | `verifiable_labs_envs` | `vlabs_sdk` |
| CLI | `vlabs-prm-eval clean-gate` | `vlabs clean-gate` |

## Import mapping (mechanical)

```python
# before
from verifiable_labs_envs.providers.dummy_provider import DummyProvider
from verifiable_labs_envs.schemas import AssuranceCardV2, ScoreSet
from verifiable_labs_envs.run_config import default_config
from verifiable_labs_envs.formal_spec.clean_promotion_gate import accept_clean_update

# after
from vlabs_sdk.providers.dummy_provider import DummyProvider
from vlabs_sdk.schemas import AssuranceCardV2, ScoreSet
from vlabs_sdk.run_config import default_config
from vlabs_sdk.formal_spec.clean_promotion_gate import accept_clean_update
```

A project-wide rename is sufficient: every module under
`verifiable_labs_envs.{providers,schemas,formal_spec}` and
`verifiable_labs_envs.run_config` exists at the same path under
`vlabs_sdk`. APIs are unchanged.

## Unreleased `0.0.3` safety migration

`vlabs clean-gate` now fails closed when a card omits any gate-critical
measurement: DCR, OOD score, hack risk, calibration, cost, or latency (the CLI
cost/latency overrides still satisfy those fields). Unit-valued measurements
must be finite and within `[0, 1]`.

The CLI now always derives `clean_vgs` from `raw_vgs`, DCR, and `--beta` using
the formal formula. A legacy card-supplied `clean_vgs` is accepted for input
compatibility but ignored, with a warning when it differs. Producers should
either omit this derived field or emit the exact canonical value.

Assurance Card v2 JSON is now the flat shape emitted by
`AssuranceCardV2.to_dict()`. `AssuranceCardV2.from_dict()` remains able to read
the earlier nested public examples (`scores`, `contamination`, and `gate`) so
stored artifacts can be migrated without a flag day. Both shapes now validate
strictly at the public boundary: booleans are JSON booleans (never truthy
strings/numbers), score and resource fields are finite and bounded, decision /
policy / redaction labels are enumerated, rejection reasons are `list[str]`,
and metadata is a finite JSON object. Serialization uses `allow_nan=False` and
revalidates metadata so a late mutation cannot emit non-standard JSON.

## What does NOT move

The 25 historical RL environments, trace schema, and training stack are not
part of `vlabs-sdk`. This package contains no environment implementations or
private engines and has no dependency on the archived legacy workspace.
