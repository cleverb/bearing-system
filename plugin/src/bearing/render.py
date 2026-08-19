"""Projection: canonical sources into runtime-native adapters.

Three projections, each justified by a real format gap:

- **subagents** -- Cursor reads `.cursor/agents/*.md` with frontmatter, Codex
  reads `.codex/agents/*.toml` requiring `name`, `description`, and
  `developer_instructions`, Claude Code reads `.claude/agents/*.md`. These are
  mutually unreadable, so a canonical definition has to compile to each.
- **rules** -- `.cursor/rules/*.mdc`, `AGENTS.md`, `CLAUDE.md`, and
  `.github/copilot-instructions.md` express substantially the same repo-level
  guidance in four incompatible formats.
- **contracts** -- one canonical Contract projects to a linter config, a CI
  check, and an agent-facing summary. None of those three is authoritative.

And one deliberate non-projection: `SKILL.md`. Agent Skills is an open standard
that Cursor, Codex, and Claude Code all read natively from `.agents/skills/`, so
there is no representational gap for a renderer to bridge. Writing one would be
solving a problem that does not exist -- `projection_necessity_errors()` below
enforces that by failing when a projection's targets all read one format.
"""

from __future__ import annotations

import os
from typing import Any, Dict, List, Optional, Sequence, Tuple

from .artifacts import Artifact, Skip
from .config import ResolvedConfig
from .paths import PLUGIN_SKILL_NAMES, plugin_root
from .util import (
    BearingError,
    emit_frontmatter,
    parse_frontmatter,
    read_text,
    toml_value,
)

# Where each target's adapters land, by projection kind and scope. Paths are
# relative to the workspace root for `repo` scope and to the home directory for
# `user` scope.
_SUBAGENT_DIRS = {
    "cursor": (".cursor/agents", ".cursor/agents"),
    "claude": (".claude/agents", ".claude/agents"),
    "codex": (".codex/agents", ".codex/agents"),
}

_RULE_TARGETS = ("cursor", "agents-md", "copilot", "claude")

# Which canonical format each target natively reads. Two targets sharing a value
# here would mean the projection between them is unnecessary.
_NATIVE_FORMATS = {
    "cursor": "cursor-md-frontmatter",
    "claude": "claude-md-frontmatter",
    "codex": "codex-toml",
    "agents-md": "plain-markdown",
    "copilot": "copilot-markdown",
    "lint": "linter-config",
    "ci": "ci-workflow",
}


class Subagent:
    def __init__(self, name: str, description: str, meta: Dict[str, Any], body: str, source: str):
        self.name = name
        self.description = description
        self.meta = meta
        self.body = body.strip() + "\n"
        self.source = source


def load_subagents(root: Optional[str] = None) -> List[Subagent]:
    """Read every canonical subagent definition from the plugin's skills."""
    root = root or plugin_root()
    found: List[Subagent] = []
    for skill_name in PLUGIN_SKILL_NAMES:
        directory = os.path.join(root, "skills", skill_name, "subagents")
        if not os.path.isdir(directory):
            continue
        for filename in sorted(os.listdir(directory)):
            if not filename.endswith(".md"):
                continue
            path = os.path.join(directory, filename)
            text = read_text(path) or ""
            front, body = parse_frontmatter(text)
            name = str(front.get("name") or os.path.splitext(filename)[0])
            description = str(front.get("description") or "").strip()
            if not description:
                raise BearingError(
                    "%s has no `description` in its frontmatter. Cursor and Codex both need one "
                    "to decide when the subagent applies, so it is required rather than optional."
                    % path
                )
            found.append(
                Subagent(
                    name=name,
                    description=description,
                    meta={
                        key: value
                        for key, value in front.items()
                        if key not in ("name", "description")
                    },
                    body=body,
                    source="plugin/skills/%s/subagents/%s" % (skill_name, filename),
                )
            )
    return found


def _scope_root(scope: str, workspace: str, ephemeral_dir: Optional[str]) -> Optional[str]:
    if scope == "repo":
        return workspace
    if scope == "user":
        return os.path.expanduser("~")
    if scope == "ephemeral":
        return ephemeral_dir
    raise BearingError("unknown projection scope %r" % scope)


def render_subagents(
    config: ResolvedConfig,
    subagents: Sequence[Subagent],
    ephemeral_dir: Optional[str] = None,
) -> Tuple[List[Artifact], List[Skip]]:
    settings = config.get("projections.subagents") or {}
    targets = list(settings.get("targets") or [])
    scope = settings.get("scope") or "user"

    artifacts: List[Artifact] = []
    skips: List[Skip] = []

    root = _scope_root(scope, config.workspace, ephemeral_dir)
    if root is None:
        skips.append(
            Skip("subagents", "*", "ephemeral scope requested with no session directory available")
        )
        return artifacts, skips

    for target in sorted(_SUBAGENT_DIRS):
        if target not in targets:
            skips.append(
                Skip(
                    "subagents",
                    target,
                    "not in projections.subagents.targets; adapters for this runtime are "
                    "intentionally not generated",
                )
            )
            continue
        repo_dir, user_dir = _SUBAGENT_DIRS[target]
        directory = os.path.join(root, user_dir if scope == "user" else repo_dir)
        for agent in subagents:
            if target == "codex":
                path = os.path.join(directory, "%s.toml" % agent.name)
                content = _codex_toml(agent)
                frontmatter_aware = False
            else:
                path = os.path.join(directory, "%s.md" % agent.name)
                content = _markdown_agent(agent, target)
                frontmatter_aware = True
            artifacts.append(
                Artifact(
                    path=path,
                    content=content,
                    source=agent.source,
                    kind="subagents",
                    target=target,
                    scope=scope,
                    frontmatter_aware=frontmatter_aware,
                )
            )

    return artifacts, skips


def _markdown_agent(agent: Subagent, target: str) -> str:
    """Cursor and Claude Code both read markdown-with-frontmatter subagents.

    Cursor documents `name`, `description`, `model`, `readonly`, and
    `is_background`. `is_background` is dropped for Claude, which does not
    document it -- emitting a field a client does not recognize is how a
    generated file starts producing warnings nobody reads.
    """
    front: Dict[str, Any] = {"name": agent.name, "description": agent.description}
    for key in ("model", "readonly", "is_background"):
        if key in agent.meta:
            if key == "is_background" and target != "cursor":
                continue
            front[key] = agent.meta[key]
    return emit_frontmatter(front) + "\n" + agent.body


def _codex_toml(agent: Subagent) -> str:
    """Codex custom agents are TOML and require `developer_instructions`.

    The markdown body becomes `developer_instructions` verbatim. That is the
    whole reason this projection exists: the same canonical prose is a document
    body in one runtime and a string-valued key in another, and no single file
    format is readable by both.
    """
    lines = [
        "name = %s" % toml_value(agent.name),
        "description = %s" % toml_value(agent.description),
    ]
    model = agent.meta.get("model")
    if model and model != "inherit":
        lines.append("model = %s" % toml_value(model))
    if agent.meta.get("readonly"):
        # Codex expresses tool restriction as a sandbox policy rather than a
        # boolean, so `readonly: true` maps onto its nearest native equivalent.
        lines.append('sandbox_policy = "read-only"')
    lines.append("developer_instructions = %s" % toml_value(agent.body.rstrip("\n")))
    return "\n".join(lines) + "\n"


def render_rules(
    config: ResolvedConfig,
    rule_body: str,
    ephemeral_dir: Optional[str] = None,
) -> Tuple[List[Artifact], List[Skip]]:
    """Project the canonical repo-level rule into each runtime's format.

    `agents-md` and `claude` are handled by the block manager in `agentsmd.py`
    rather than here, because those two files are hand-maintained by the
    repository and BEARING owns only a delimited region inside them. Overwriting
    someone's AGENTS.md wholesale would be the fastest possible way to get
    BEARING removed from a repository.
    """
    settings = config.get("projections.rules") or {}
    targets = list(settings.get("targets") or [])
    scope = settings.get("scope") or "repo"

    artifacts: List[Artifact] = []
    skips: List[Skip] = []
    root = _scope_root(scope, config.workspace, ephemeral_dir)
    if root is None:
        skips.append(Skip("rules", "*", "ephemeral scope requested with no session directory"))
        return artifacts, skips

    for target in _RULE_TARGETS:
        if target not in targets:
            skips.append(
                Skip("rules", target, "not in projections.rules.targets")
            )
            continue

        if target == "cursor":
            front = {
                "description": "BEARING decision-system rules: where authoritative decisions "
                "live, when to escalate, and what may never block a merge.",
                "alwaysApply": True,
            }
            artifacts.append(
                Artifact(
                    path=os.path.join(root, ".cursor", "rules", "bearing.mdc"),
                    content=emit_frontmatter(front) + "\n" + rule_body,
                    source="plugin/src/bearing/data/templates/agents-block.md",
                    kind="rules",
                    target=target,
                    scope=scope,
                    frontmatter_aware=True,
                )
            )
        elif target == "copilot":
            artifacts.append(
                Artifact(
                    path=os.path.join(root, ".github", "copilot-instructions.md"),
                    content=rule_body,
                    source="plugin/src/bearing/data/templates/agents-block.md",
                    kind="rules",
                    target=target,
                    scope=scope,
                )
            )
        else:
            skips.append(
                Skip(
                    "rules",
                    target,
                    "managed as a delimited block inside a hand-maintained file by "
                    "`bearing render`, not written as a whole generated file",
                )
            )

    return artifacts, skips


def projection_necessity_errors(config: ResolvedConfig) -> List[str]:
    """Fail when a projection bridges no actual format gap.

    The architecture's rule is that Projection applies only where a runtime
    cannot read the canonical format, and that any new artifact type must be
    checked against that rule rather than assumed to need a renderer. This is
    that check, executable: a projection whose targets all consume one identical
    format is redundant machinery, and redundant machinery is how a clean
    principle turns into a pile of renderers nobody can justify.
    """
    errors: List[str] = []
    for kind in ("subagents", "rules", "contracts"):
        # Distinct targets, because a target listed twice is a typo in a config
        # file rather than a redundant renderer, and reporting it as the latter
        # would send the reader looking for a design flaw that is not there.
        targets = sorted(set((config.get("projections.%s" % kind) or {}).get("targets") or []))
        if len(targets) < 2:
            continue
        formats = {_NATIVE_FORMATS.get(target, target) for target in targets}
        if len(formats) == 1:
            errors.append(
                "projection %r targets %s, which all consume the same format (%s). "
                "Projection is only justified by a real format gap; drop the renderer and "
                "let the canonical file stand alone."
                % (kind, ", ".join(sorted(targets)), formats.pop())
            )
    return errors


def skill_projection_errors(root: Optional[str] = None) -> List[str]:
    """Assert nobody has added a SKILL.md renderer.

    Agent Skills is an open standard read natively from `.agents/skills/` by
    every runtime BEARING targets. A renderer here would be the exact mistake
    the architecture warns about, and it is cheap to make by accident when
    surrounded by other renderers -- so it is checked.
    """
    root = root or plugin_root()
    offenders: List[str] = []
    for skill_name in PLUGIN_SKILL_NAMES:
        scripts = os.path.join(root, "skills", skill_name, "scripts")
        if not os.path.isdir(scripts):
            continue
        for filename in sorted(os.listdir(scripts)):
            lowered = filename.lower()
            if "render" in lowered and "skill" in lowered:
                offenders.append(os.path.join("skills", skill_name, "scripts", filename))
    return [
        "%s looks like a SKILL.md renderer. Agent Skills is an open standard that Cursor, "
        "Codex, and Claude Code all read natively; there is no format gap to bridge and the "
        "canonical SKILL.md is the consumable artifact." % path
        for path in offenders
    ]
