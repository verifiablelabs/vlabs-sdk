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
pip install vlabs-sdk
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

The gate fails closed if DCR, OOD, hack-risk, calibration, cost, or latency
evidence is missing. It validates unit-valued metrics and recomputes
`clean_vgs` from `raw_vgs`, DCR, and `--beta`; a caller-supplied derived value
cannot override that formula. See [MIGRATION.md](MIGRATION.md) for the `0.0.3`
card migration.

`AssuranceCardV2.from_dict()` is a strict JSON trust boundary. It rejects
truthy boolean coercions, NaN/Infinity, out-of-range scores, negative resource
measurements, unknown decision/policy/redaction labels, malformed reason lists,
and non-JSON metadata. `to_dict()` revalidates mutable metadata and never emits
non-standard NaN/Infinity tokens.

## What ships here

| Surface | Path |
|---|---|
| Run config — modes `evaluate_only` / `gate_only` / `improve_and_gate` / `substrate`, privacy-preserving defaults | `src/vlabs_sdk/run_config.py` |
| Provider interface + dummy provider (`validate_config` / `estimate_cost` / `run` / `dry_run`) | `src/vlabs_sdk/providers/` |
| Schemas — EvaluationContract, ScoreSet, TransferMetrics, GateOutcome, AssuranceCard v2, split policy | `src/vlabs_sdk/schemas/` |
| Formal-spec math mirror (clean score, CleanVGS, generalization gap, 8-condition promotion gate) | `src/vlabs_sdk/formal_spec/` |
| `vlabs clean-gate` CLI (ACCEPT exit 0 / REJECT exit 1) | `tools/vlabs-prm-eval/` |

This split repository is canonical for the public SDK surface; historical
import provenance is documented in [PROVENANCE.md](PROVENANCE.md).

## Evidence

Public **synthetic / redacted** demo evidence and separately labelled real
public-benchmark results live in
[vlabs-evidence](https://github.com/verifiablelabs/vlabs-evidence) and on
Hugging Face: <https://huggingface.co/datasets/verifiablelabs/vlabs-clean-gate-evidence>.
The HF demo dataset is not a training dataset; neither surface contains
customer data, hidden evals, gold answers, raw traces, private traps, or private
engine internals.

## Formal scope

Selected mathematical properties behind the contamination-resistant
promotion gate are machine-verified in Lean 4. A hand-maintained Python mirror
has property tests derived from selected definitions; no mechanized
code-to-proof parity is claimed.

## License

Apache-2.0.
