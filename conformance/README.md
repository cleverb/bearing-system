# Tier 4 client conformance

Tier 4 qualifies a release against real runtime clients. It is a release gate,
not a pull-request gate. Evidence records bind observed client behavior to the
BEARING compatibility API, renderer/schema versions, client range, and only the
artifacts exercised by that runtime.

For each runtime, install the release candidate in a scratch repository and
observe all six checks: installation, Skill discovery, agent acceptance, hook
execution, the read-only plugin boundary, and uninstall preservation. Record the
result with `scripts/conformance/run.py`; the recorder refuses partial evidence.

`bearing package --release-check` accepts only passing, schema-valid evidence
whose compatibility fingerprint is still current.

The runtime itself must be involved; schema validation alone is Tier 1. For
Claude Code, for example, use a scratch Git repository, add this checkout as a
local marketplace, install `bearing@bearing`, inspect `claude plugin details`,
run a read-only headless session that exercises a governed file, verify the
digest under `.bearing/runtime/context/`, then uninstall and confirm decision
content remains. Cursor currently requires its GUI marketplace path for plugin
qualification; the recorder accepts that manual observation through the same
schema. Codex qualification uses its plugin marketplace commands. Never mark a
check passing merely because its manifest looked plausible.

Example after all six behaviors were observed:

```bash
python3 scripts/conformance/run.py --runtime claude \
  --pass-check install --pass-check skill_discovery \
  --pass-check agent_acceptance --pass-check hook_execution \
  --pass-check readonly_boundary --pass-check uninstall_preservation \
  --notes "scratch-repository qualification notes"
```
