"""BEARING: an EOCR-based decision system for human-agent engineering.

@see ADR-0005 — version constants live in this stdlib-only package, not in a
dependency metadata extra.

The version here is the single source of truth for the version stamped into
generated artifacts, manifests, and the projection lock file. `bearing package`
propagates it into every generated manifest, so no manifest carries a
hand-maintained version number.
"""

__version__ = "0.1.0"

# Bumped independently of __version__, and only when the *output* of a renderer
# changes. A renderer-version bump invalidates every artifact in
# .bearing/projections.lock.json and is what makes `bearing render --check`
# report drift after an upgrade that changed generated formatting.
RENDERER_VERSION = 2

# Bumped only on a breaking change to .bearing/config.json.
CONFIG_VERSION = 1
