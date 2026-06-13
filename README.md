# vlabs-sdk

> Verifiable Labs builds clean feedback and promotion gates for increasingly general AI agents.

SDK contracts for the Verifiable Labs platform: run configuration, the
model-provider interface, and the typed schemas that evaluation contracts,
score sets, gate outcomes, and assurance cards are built from.

- **pip package:** `vlabs-sdk`
- **import package:** `vlabs_sdk`
- **CLI:** `vlabs` (clean promotion gate)

## Install

```bash
pip install vlabs-sdk        # once published; until then:
pip install "vlabs-sdk @ git+https://github.com/verifiablelabs/vlabs-sdk@main"
```

```python
from vlabs_sdk.providers.dummy_provider import DummyProvider
from vlabs_sdk.providers.base import ModelRequest
from vlabs_sdk.schemas import AssuranceCardV2, ScoreSet, TransferMetrics
from vlabs_sdk.run_config import default_config
from vlabs_sdk.formal_spec.clean_promotion_gate import accept_clean_update
```

Migrating from the legacy `verifiable-labs-envs` package? See
[MIGRATION.md](MIGRATION.md).

## clean-gate CLI

The `vlabs` CLI ships **with** the `vlabs-sdk` distribution — no extra
install:

```bash
pip install vlabs-sdk
vlabs --help
vlabs clean-gate --old baseline.json --new candidate.json
# exit 0 = ACCEPT, exit 1 = REJECT (reasons printed)
```

The CLI is implemented in the bundled `vlabs_prm_eval` package (depends
only on `vlabs_sdk` + `typer`); both import packages are included in the
wheel.

## What ships here

| Surface | Path |
|---|---|
| Run config — modes `evaluate_only` / `gate_only` / `improve_and_gate` / `substrate`, privacy-preserving defaults | `src/vlabs_sdk/run_config.py` |
| Provider interface + dummy provider (`validate_config` / `estimate_cost` / `run` / `dry_run`) | `src/vlabs_sdk/providers/` |
| Schemas — EvaluationContract, ScoreSet, TransferMetrics, GateOutcome, AssuranceCard v2, split policy | `src/vlabs_sdk/schemas/` |
| Formal-spec math mirror (clean score, CleanVGS, generalization gap, 8-condition promotion gate) | `src/vlabs_sdk/formal_spec/` |
| `vlabs clean-gate` CLI (ACCEPT exit 0 / REJECT exit 1) | `tools/vlabs-prm-eval/` |

This repository is a mirror of the canonical monorepo with the import
namespace remapped (see [PROVENANCE.md](PROVENANCE.md)); it becomes
canonical at split-flip time.

## Formal scope

Selected mathematical properties behind the contamination-resistant
promotion gate are machine-verified in Lean 4. The implementation is
property-tested against the formal specification.

## License

Apache-2.0.
