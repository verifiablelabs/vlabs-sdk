# vlabs-sdk

> Verifiable Labs builds clean feedback and promotion gates for increasingly general AI agents.

SDK contracts for the Verifiable Labs platform: run configuration, the
model-provider interface, and the typed schemas that evaluation contracts,
score sets, gate outcomes, and assurance cards are built from.

**Status: pointer repository.** The implementation currently lives in
[verifiable-labs-envs](https://github.com/verifiablelabs/verifiable-labs-envs)
and will move here only when the split can be done without destabilizing
the working implementation.

| Surface | Current location (in `verifiable-labs-envs`) |
|---|---|
| Run config — modes `evaluate_only` / `gate_only` / `improve_and_gate` / `substrate`, privacy-preserving defaults | `src/verifiable_labs_envs/run_config.py` |
| Provider interface + dummy provider (`validate_config` / `estimate_cost` / `run` / `dry_run`) | `src/verifiable_labs_envs/providers/` |
| Schemas — EvaluationContract, ScoreSet, TransferMetrics, GateOutcome, AssuranceCard v2, split policy | `src/verifiable_labs_envs/schemas/` |
| `clean-gate` CLI (ACCEPT exit 0 / REJECT exit 1) | `tools/vlabs-prm-eval/` |

## Formal scope

Selected mathematical properties behind the contamination-resistant promotion gate are machine-verified in Lean 4. The implementation is property-tested against the formal specification.

## License

Apache-2.0.
