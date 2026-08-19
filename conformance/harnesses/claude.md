# Claude Code qualification

Use a fresh Git repository and local-scoped marketplace configuration. Validate
the plugin, install `bearing@bearing`, and inspect `claude plugin details`; it
must report all three Skills and both `UserPromptSubmit` and `PreToolUse` hooks.

Initialize the scratch repository with the release-candidate CLI, add an
Accepted Contract and a matching source file, and render the projected agents.
Run a read-only headless Claude session whose prompt names that source file. A
session digest must appear under `.bearing/runtime/context/` before any tool is
used. Run a second session that reads the file to exercise `PreToolUse`.

Hash the installed plugin before and after both sessions to prove the read-only
boundary. Uninstall locally and confirm the authored decision, index, shadow
graph, and projected repository agents remain. Record all six results with
`scripts/conformance/run.py --runtime claude`.
