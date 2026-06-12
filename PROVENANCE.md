# Provenance

Clean import (no history rewrite) from `verifiablelabs/verifiable-labs-envs`
at commit `762b44e8019af3e89c55bba0f88e9157bb50c5c3` (main). Mirrored paths: `src/verifiable_labs_envs/{providers,schemas,formal_spec,run_config.py}`, `tests/sdk/`, `tools/vlabs-prm-eval/` (clean-gate CLI).

The source monorepo remains canonical until the split flips; this mirror is
refreshed by the migration tooling documented in
`verifiable-labs-private/docs/ops/github-repo-split-migration.md`.

The import namespace is remapped during staging: the canonical
`verifiable_labs_envs` subset ships here as `vlabs_sdk` (CLI: `vlabs`).
See MIGRATION.md.
