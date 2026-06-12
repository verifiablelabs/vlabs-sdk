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

## What does NOT move

The 25 RL environments, the trace schema, and the training stack stay in
the legacy [`verifiable-labs-envs`](https://github.com/verifiablelabs/verifiable-labs-envs)
package/repository (compatibility/legacy workspace). `vlabs-sdk` contains
no environment implementations, no private engines, and depends on
neither.
