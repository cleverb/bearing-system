<!-- DO NOT EDIT. Generated from plugin/plugin.json by bearing 0.1.0. Run `bearing render` to update; edits here are overwritten and reported as drift by `bearing render --check`. -->

# Generated directory — do not edit

Every file here is generated from `plugin/plugin.json` by `bearing package`.

Claude Code reads a plugin manifest from `.claude-plugin/plugin.json`.

JSON has no comment syntax, so the do-not-edit notice lives here rather than inside the files themselves. Injecting a marker key was rejected: a plugin manifest that a client might reject for an unknown top-level field is not worth a cosmetic warning, and `.bearing/projections.lock.json` already records the hash and source of every generated file.

Change `plugin/plugin.json` and re-run `bearing package`. `bearing package --check` fails CI on drift.
