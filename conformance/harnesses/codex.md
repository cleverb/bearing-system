# Codex qualification

Use an isolated Codex profile or disposable machine. Add this checkout as a
local marketplace, install the release candidate, and use `codex plugin list
--json` to confirm the plugin and its three Skills are accepted. Initialize a
scratch repository and confirm the generated `.codex/agents/*.toml` files are
accepted in a real session.

Codex is currently declared `session-advisory`, so hook execution means
confirming that no unsupported path-aware hook is claimed. Hash the installed
plugin before and after the session, remove the plugin and marketplace, and
confirm repository decision content and projected agents remain. Record all six
results with `scripts/conformance/run.py --runtime codex`.

Do not run this harness against a maintainer's normal profile unless its current
marketplaces and installed plugins were inventoried and can be restored exactly.
