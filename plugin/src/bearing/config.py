"""Config resolution.

Five layers, and one rule that decides which of them wins.

The naive approach -- "nearest file wins" -- breaks immediately in practice. A
developer who sets a preferred model in `~/.bearing/config.json` does not expect
every repository to silently override it, and a repository that declares its
decisions live in `docs/adr/` must not be overridable by a personal preference
for `docs/decisions/`. Nearness is the wrong axis.

The rule BEARING uses instead:

- A **repo fact** describes the repository: where decisions live, what the
  scope is, what may block a merge, which projection targets are generated.
  Repository config wins.
- An **operator fact** describes the person or machine running the tool: model
  choices, reviewer cost rate, whether adapters get written into the working
  tree. User config wins.

Every leaf key is classified as exactly one of the two. An unclassified key is a
hard error rather than a precedence guess -- if a new setting does not obviously
belong to the repo or the operator, that ambiguity is a design problem to settle
in code review, not at runtime.
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

from . import CONFIG_VERSION
from . import jsonschema
from .paths import Layout, data_dir, find_workspace_root, user_root
from .util import BearingError, flatten, read_json, unflatten

REPO_FACT = "repo"
OPERATOR_FACT = "operator"

# Written into generated config so editors offer completion and validation.
# A URL rather than a relative path: the schema ships inside the plugin, and a
# relative path from a target repository into a plugin cache directory would
# break on the next plugin update.
SCHEMA_URL = "https://bearing.dev/schemas/config-1.json"

# Longest matching prefix wins, so a specific key can override its section.
_CLASSIFICATION: Tuple[Tuple[str, str], ...] = (
    ("version", REPO_FACT),
    ("decisions", REPO_FACT),
    ("scope", REPO_FACT),
    ("profile", REPO_FACT),
    ("skills", REPO_FACT),
    ("enforcement", REPO_FACT),
    ("verify", REPO_FACT),
    ("interview.transcripts.retention", REPO_FACT),
    ("review", REPO_FACT),
    # Which runtimes a repository generates adapters for is a property of the
    # repository; where those adapters land is a property of the operator.
    ("projections", REPO_FACT),
    ("projections.subagents.scope", OPERATOR_FACT),
    ("projections.rules.scope", OPERATOR_FACT),
    ("projections.contracts.scope", OPERATOR_FACT),
    ("models", OPERATOR_FACT),
    ("cost", OPERATOR_FACT),
    # A hard spend cap protects the repository's budget, not the operator's
    # preference, so it is the one cost key the repository owns.
    ("cost.budget_usd_per_run", REPO_FACT),
)

LAYER_DEFAULTS = "defaults"
LAYER_USER = "user"
LAYER_REPO = "repo"
LAYER_LOCAL = "local"
LAYER_ENV = "env"
LAYER_FLAGS = "flags"

# Order within each class, lowest precedence first.
_ORDER = {
    REPO_FACT: [LAYER_DEFAULTS, LAYER_USER, LAYER_REPO, LAYER_LOCAL, LAYER_ENV, LAYER_FLAGS],
    OPERATOR_FACT: [LAYER_DEFAULTS, LAYER_REPO, LAYER_USER, LAYER_LOCAL, LAYER_ENV, LAYER_FLAGS],
}


def classify(dotted: str) -> Optional[str]:
    best: Optional[str] = None
    best_len = -1
    for prefix, kind in _CLASSIFICATION:
        if dotted == prefix or dotted.startswith(prefix + "."):
            if len(prefix) > best_len:
                best, best_len = kind, len(prefix)
    return best


def default_config() -> Dict[str, Any]:
    path = os.path.join(data_dir(), "config.default.json")
    data = read_json(path)
    if data is None:
        raise BearingError("packaged defaults missing at %s" % path)
    data.pop("$schema", None)
    return data


def config_schema() -> Dict[str, Any]:
    return read_json(os.path.join(data_dir(), "config.schema.json"), {}) or {}


def env_overrides(environ: Optional[Dict[str, str]] = None) -> Dict[str, Any]:
    """Read `BEARING_*` variables into config keys.

    `BEARING_DECISIONS_PATH=docs/adr` sets `decisions.path`. Matching is done
    against the known key set rather than by mechanical underscore splitting,
    because `price_book_max_age_days` would otherwise be unrepresentable.
    """
    environ = os.environ if environ is None else environ
    known = list(flatten(default_config()).keys())
    lookup = {"BEARING_" + key.replace(".", "_").replace("-", "_").upper(): key for key in known}
    out: Dict[str, Any] = {}
    for name, raw in environ.items():
        if not name.startswith("BEARING_") or name in ("BEARING_HOME",):
            continue
        key = lookup.get(name)
        if key is None:
            continue
        try:
            out[key] = json.loads(raw)
        except (TypeError, ValueError):
            out[key] = raw
    return out


class ResolvedConfig:
    def __init__(
        self,
        data: Dict[str, Any],
        provenance: Dict[str, str],
        sources: Dict[str, Optional[str]],
        warnings: List[str],
        errors: List[str],
        workspace: str,
    ) -> None:
        self.data = data
        self.provenance = provenance
        self.sources = sources
        self.warnings = warnings
        self.errors = errors
        self.workspace = workspace
        self.layout = Layout(workspace, data)

    def get(self, dotted: str, default: Any = None) -> Any:
        cursor: Any = self.data
        for part in dotted.split("."):
            if not isinstance(cursor, dict) or part not in cursor:
                return default
            cursor = cursor[part]
        return cursor

    def origin(self, dotted: str) -> str:
        return self.provenance.get(dotted, LAYER_DEFAULTS)

    @property
    def initialized(self) -> bool:
        return self.sources.get(LAYER_REPO) is not None

    def require_initialized(self) -> None:
        if not self.initialized:
            raise BearingError(
                "this workspace is not initialized for BEARING.\n"
                "  Run `bearing init` first -- it detects your decision-record convention\n"
                "  and writes .bearing/config.json without guessing."
            )


def resolve(
    workspace: Optional[str] = None,
    flags: Optional[Dict[str, Any]] = None,
    environ: Optional[Dict[str, str]] = None,
) -> ResolvedConfig:
    workspace = os.path.abspath(workspace or find_workspace_root())

    user_file = os.path.join(user_root(), "config.json")
    repo_file = os.path.join(workspace, ".bearing", "config.json")
    local_file = os.path.join(workspace, ".bearing", "config.local.json")

    raw_layers: Dict[str, Dict[str, Any]] = {
        LAYER_DEFAULTS: default_config(),
        LAYER_USER: read_json(user_file, {}) or {},
        LAYER_REPO: read_json(repo_file, {}) or {},
        LAYER_LOCAL: read_json(local_file, {}) or {},
        LAYER_ENV: unflatten(env_overrides(environ)),
        LAYER_FLAGS: unflatten(flags or {}),
    }

    sources: Dict[str, Optional[str]] = {
        LAYER_DEFAULTS: os.path.join(data_dir(), "config.default.json"),
        LAYER_USER: user_file if os.path.isfile(user_file) else None,
        LAYER_REPO: repo_file if os.path.isfile(repo_file) else None,
        LAYER_LOCAL: local_file if os.path.isfile(local_file) else None,
        LAYER_ENV: "environment" if raw_layers[LAYER_ENV] else None,
        LAYER_FLAGS: "command line" if raw_layers[LAYER_FLAGS] else None,
    }

    flat_layers = {name: flatten(data) for name, data in raw_layers.items()}

    warnings: List[str] = []
    errors: List[str] = []

    unclassified = sorted(
        {
            key
            for name, layer in flat_layers.items()
            if name != LAYER_DEFAULTS
            for key in layer
            if classify(key) is None
        }
    )
    for key in unclassified:
        errors.append(
            "config key %r is not classified as a repo fact or an operator fact, "
            "so its precedence is undefined. Add it to _CLASSIFICATION in config.py." % key
        )

    resolved_flat: Dict[str, Any] = {}
    provenance: Dict[str, str] = {}

    all_keys = set()
    for layer in flat_layers.values():
        all_keys.update(layer)

    for key in sorted(all_keys):
        kind = classify(key)
        if kind is None:
            continue
        for layer_name in _ORDER[kind]:
            if key in flat_layers[layer_name]:
                resolved_flat[key] = flat_layers[layer_name][key]
                provenance[key] = layer_name

    # A repo fact set in config.local.json still applies -- it is an escape
    # hatch and removing it would just push people to edit the committed file --
    # but it is called out, because it silently makes one machine behave
    # differently from every other clone of the repository.
    for key in sorted(flat_layers[LAYER_LOCAL]):
        if classify(key) == REPO_FACT and provenance.get(key) == LAYER_LOCAL:
            warnings.append(
                "%s is a repo fact overridden in .bearing/config.local.json; it applies "
                "on this machine only and no one else's clone will behave this way" % key
            )

    data = unflatten(resolved_flat)

    if data.get("version") != CONFIG_VERSION:
        errors.append(
            "config version is %r but this BEARING expects %r"
            % (data.get("version"), CONFIG_VERSION)
        )

    schema = config_schema()
    if schema:
        for message in jsonschema.validate(data, schema):
            errors.append("config: %s" % message)

    errors.extend(_semantic_errors(data))

    return ResolvedConfig(data, provenance, sources, warnings, errors, workspace)


def _semantic_errors(data: Dict[str, Any]) -> List[str]:
    """Checks the schema cannot express, because they are cross-field."""
    errors: List[str] = []

    decisions_path = ((data.get("decisions") or {}).get("path") or "").strip()
    if not decisions_path:
        errors.append("decisions.path must not be empty")
    elif os.path.isabs(decisions_path) or decisions_path.startswith(".."):
        errors.append(
            "decisions.path must be inside the workspace (found %r)" % decisions_path
        )

    block_on = (data.get("enforcement") or {}).get("block_on") or []
    if "recovery_signal" in block_on:
        errors.append(
            "enforcement.block_on may not include 'recovery_signal'. A confidence score is a "
            "statement about evidence, not a statement of organizational authority; blocking "
            "authority belongs only to structural or accepted-Contract enforcement."
        )

    skills = data.get("skills") or {}
    if skills.get("source") == "vendored" and not skills.get("vendored_version"):
        errors.append(
            "skills.source is 'vendored' but skills.vendored_version is unset, so the Skill "
            "version that produced a candidate cannot be reconstructed. Re-run `bearing vendor`."
        )

    return errors


def write_repo_config(
    layout: Layout, data: Dict[str, Any], include_operator_keys: Optional[List[str]] = None
) -> bool:
    """Persist repo config, keeping only keys the repository should own.

    Operator facts are stripped rather than written with their resolved values.
    That distinction matters: `bearing init` resolves a model choice from the
    operator's own `~/.bearing/config.json`, and writing that resolved value into
    a committed file would quietly turn one developer's preference into a
    repository default for everyone.

    A repository may still *declare* an operator-fact default deliberately -- a
    monorepo that wants adapters committed for every contributor, say -- by
    passing the key explicitly. Precedence is unaffected: user config still wins
    over a repository's suggestion for operator facts.
    """
    from .util import write_json

    flat = flatten(data)
    keep = {key: value for key, value in flat.items() if classify(key) == REPO_FACT}
    for key in include_operator_keys or []:
        for candidate, value in flat.items():
            if candidate == key or candidate.startswith(key + "."):
                keep[candidate] = value
    out = unflatten(keep)
    out["$schema"] = SCHEMA_URL
    out["version"] = CONFIG_VERSION
    return write_json(layout.config_file, out)
