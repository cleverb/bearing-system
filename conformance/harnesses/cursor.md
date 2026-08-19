# Cursor qualification

Cursor's current agent CLI does not expose plugin marketplace installation, so
qualification uses a disposable Cursor profile and the GUI marketplace flow.
Install this checkout as a local marketplace, confirm all three Skills and the
projected agents are accepted, then open a scratch repository and verify the
declared `workspaceOpen` behavior.

Cursor remains `session-advisory`; do not infer pre-mutation path awareness from
workspace-open projection. Hash the installed plugin before and after the
session, uninstall it, and confirm repository decision content and projections
remain. Record the manual observations through
`scripts/conformance/run.py --runtime cursor`; the evidence schema is identical
to automated qualification.
