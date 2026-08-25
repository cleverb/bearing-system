# MCP App preview catalog

Local mock host for Recovery and Reviewable MCP Apps. Not Storybook. Not a visual merge gate.

```bash
PYTHONPATH=plugin/src python3 -m bearing ui-preview --open
```

Default bind is `127.0.0.1:8765`. The command does not require `bearing init` and does not write workspace config.

## What you edit

| Path | Role |
| --- | --- |
| `catalog.json` | Story map. Add a row here when Recovery or Review gains a banner, empty view, density extreme, validation error, or new disposition. |
| `fixtures/recovery/**` | Full status payloads (schema + `stages`, `recent_activity`, `scope.locations`). |
| `fixtures/reviewable/*.json` | `structuredContent` with `candidates`, `enums`, `workspace`. |
| `host.html` | Mock MCP parent (sidebar, clock, postMessage JSON-RPC). |

Do not rewrite App JS to animate. Recovery motion is fixture playback on the host clock.

## Recovery simulation clock

Lifecycle stories advance on a **5s** host clock (catalog `defaults.simulation.interval_ms`, overridable per story or with `--sim-ms`). Chrome: play / pause / reset / step, speed 0.5x–4x.

The parent holds the frame index. Reloading the iframe reboots the App and shows the current stage; it does not rewind the run. Loop: after the completed frame is held for one interval, the host posts `ui/notifications/tool-result` with frame 0 so `render()` wakes even after the App stopped polling.

Frozen stories have `fixture` only (no `simulation`).

## Story matrix (keep current)

When App markup or behavior adds a UI state, add or extend a catalog story in the same change. A unittest asserts every `stories[].id` has resolvable fixtures that validate.

**Recovery runs:** `recovery-run-empty`, `recovery-run-few`, `recovery-run-dense`, `recovery-run-constrained`, `recovery-run-failed`.

**Recovery frozen:** `recovery-idle`, `recovery-constrained`, `recovery-failed`, `recovery-few-midscan`.

**Review:** `review-empty`, `review-few`, `review-dense`, `review-needs-disposition`, `review-promote-invalid`, `review-dispositions`.

## Flags vs catalog vs config

- Catalog/fixtures: named UI states, copy, density, which App, evaluator notes.
- CLI flags: `--port`, `--bind`, `--open`, `--list`, `--story`, `--catalog`, `--fixtures`, `--html-root`, `--sim-ms`.
- Not in `.bearing/config.json` / `bearing.yaml`.

`--html-root` loads App HTML, CSS, JS, and SVG from a checkout `plugin/src/bearing/data` (templates under `templates/html`, assets under `assets/`) while the installed CLI is a packaged copy.
