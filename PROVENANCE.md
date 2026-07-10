# Provenance

Clean import (no history rewrite) from the archived legacy workspace at commit
`762b44e8019af3e89c55bba0f88e9157bb50c5c3`. Imported paths covered the
provider/schema/formal-spec/run-config surface, SDK tests, and clean-gate CLI.

`vlabs-sdk` is now canonical for this public surface.

The imported namespace was remapped to `vlabs_sdk` (CLI: `vlabs`) so it can be
installed alongside historical environments without a collision. See
MIGRATION.md.
