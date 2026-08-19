"""Manifest projection: one canonical `plugin.json`, many client manifests.

@see ADR-0003 — BEARING's own distribution is the first test of Projection.

BEARING's own distribution is the first test of its own Projection principle. The
canonical source is `plugin/plugin.json` in the Agent Plugins v1.0.0 format --
the vendor-neutral floor, whose closed schema permits exactly `$schema`, `name`,
`version`, `description`, `author`, `homepage`, `repository`, `license`,
`keywords`, and `extensions`.

Every client manifest is generated from it:

    plugin/plugin.json                    canonical
        |
        +-- plugin/.cursor-plugin/plugin.json
        +-- plugin/.claude-plugin/plugin.json
        +-- plugin/.codex-plugin/plugin.json
        +-- plugin/skills/*/agents/openai.yaml
        +-- .cursor-plugin/marketplace.json   (repo root -- the repo *is* the marketplace)
        +-- .claude-plugin/marketplace.json

This is a genuine format gap, not projection for its own sake: the three clients
read manifests from three different fixed locations and none of them reads the
others'. The Cursor and Claude Code marketplace schemas happen to be nearly
identical, which is why one generator covers both cheaply -- but "nearly" is
doing work, so they are emitted separately rather than symlinked.
"""

from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Sequence, Tuple

from .artifacts import Artifact, Skip, generated_dir_notice
from .paths import PLUGIN_SKILL_NAMES
from .util import BearingError, dump_json, parse_frontmatter, read_json, read_text

MARKETPLACE_NAME = "bearing"
# Human-facing product title. Cursor `name` must stay lowercase kebab-case;
# `displayName` is what the marketplace UI shows.
PRODUCT_DISPLAY_NAME = "BEARING"

# Reserved by Anthropic for official use; a third-party marketplace using one
# stops loading and reports as an untrusted source.
CLAUDE_RESERVED_MARKETPLACE_NAMES = frozenset(
    {
        "claude-code-marketplace",
        "claude-code-plugins",
        "claude-plugins-official",
        "claude-plugins-community",
        "claude-community",
        "anthropic-marketplace",
        "anthropic-plugins",
        "agent-skills",
        "anthropic-agent-skills",
        "knowledge-work-plugins",
        "life-sciences",
        "claude-for-legal",
        "claude-for-financial-services",
        "financial-services-plugins",
        "first-party-plugins",
        "healthcare",
    }
)

AGENT_PLUGINS_SCHEMA = "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json"

# Agent Plugins v1.0.0 section 5.2: the manifest schema is closed.
CANONICAL_FIELDS = (
    "$schema",
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
    "extensions",
)

# Fields the client manifests share with the canonical one. Component paths are
# omitted from the shared projection: in Cursor, specifying a component path
# *replaces* folder discovery rather than adding to it, so a stale explicit
# entry silently hides skills. Cursor-only manifests therefore use the same
# conventional directory paths auto-discovery would find (`./skills/`, etc.),
# which lets the marketplace UI link to GitHub without changing what installs.
CURSOR_SKILLS_PATH = "./skills/"
SHARED_FIELDS = (
    "name",
    "version",
    "description",
    "author",
    "homepage",
    "repository",
    "license",
    "keywords",
)

_NAME_RE = re.compile(r"^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$")


def load_canonical(plugin_root: str) -> Dict[str, Any]:
    path = os.path.join(plugin_root, "plugin.json")
    data = read_json(path)
    if data is None:
        raise BearingError("no canonical manifest at %s" % path)
    for message in validate_canonical(data):
        raise BearingError("plugin.json: %s" % message)
    return data


def validate_canonical(data: Dict[str, Any]) -> List[str]:
    """Enforce the parts of the closed schema that matter for installability."""
    errors: List[str] = []

    if data.get("$schema") != AGENT_PLUGINS_SCHEMA:
        errors.append(
            "$schema must be exactly %r (Agent Plugins v1.0.0 requires the canonical "
            "identifier; clients select validation rules from it and must not fetch it)"
            % AGENT_PLUGINS_SCHEMA
        )

    unknown = sorted(set(data) - set(CANONICAL_FIELDS))
    if unknown:
        errors.append(
            "unknown top-level field(s) %s -- the Agent Plugins manifest schema is closed; "
            "client-specific data belongs under `extensions`" % ", ".join(repr(k) for k in unknown)
        )

    name = data.get("name")
    if not isinstance(name, str) or not name:
        errors.append("name is required and must be a non-empty string")
    else:
        if not 1 <= len(name) <= 64:
            errors.append("name must be 1-64 characters (found %d)" % len(name))
        if not _NAME_RE.match(name):
            errors.append(
                "name %r must be lowercase alphanumeric, hyphens, and periods only, "
                "and must start and end alphanumeric" % name
            )
        if "--" in name or ".." in name:
            errors.append("name %r must not contain consecutive hyphens or periods" % name)

    author = data.get("author")
    if author is not None:
        if not isinstance(author, dict):
            errors.append("author must be an object")
        else:
            extra = sorted(set(author) - {"name", "email", "url"})
            if extra:
                errors.append(
                    "author may contain only name, email, url (found %s)" % ", ".join(extra)
                )

    return errors


def _shared(data: Dict[str, Any]) -> Dict[str, Any]:
    return {key: data[key] for key in SHARED_FIELDS if key in data}


def plugin_manifests(plugin_root: str, canonical: Dict[str, Any]) -> List[Artifact]:
    """The three client-native plugin manifests, inside the plugin directory."""
    source = "plugin/plugin.json"
    out: List[Artifact] = []

    for directory, what in (
        (
            ".cursor-plugin",
            "Cursor reads a plugin manifest from `.cursor-plugin/plugin.json`. This format "
            "is required (rather than the bare Agent Plugins `plugin.json`) because BEARING "
            "ships subagents and hooks, which the portable v1.0.0 format does not cover.",
        ),
        (
            ".claude-plugin",
            "Claude Code reads a plugin manifest from `.claude-plugin/plugin.json`.",
        ),
        (
            ".codex-plugin",
            "Codex reads a plugin manifest from `.codex-plugin/plugin.json`.",
        ),
    ):
        body = _shared(canonical)
        if directory == ".cursor-plugin":
            # Claude reserves hooks/hooks.json as its convention. Cursor can
            # name its component path explicitly, keeping the incompatible
            # schemas out of the same file.
            body["hooks"] = "./hooks/cursor.json"
            # Same path auto-discovery would use; required for marketplace GitHub links.
            body["skills"] = CURSOR_SKILLS_PATH
            # Cursor-only: marketplace title. `name` stays the install id.
            body["displayName"] = PRODUCT_DISPLAY_NAME
        out.append(
            Artifact(
                path=os.path.join(plugin_root, directory, "plugin.json"),
                content=dump_json(body),
                source=source,
                kind="manifest",
                target=directory.strip("."),
                scope="package",
            )
        )
        out.append(
            Artifact(
                path=os.path.join(plugin_root, directory, "GENERATED.md"),
                content=generated_dir_notice(what),
                source=source,
                kind="manifest",
                target=directory.strip("."),
                scope="package",
            )
        )

    return out


def marketplace_manifests(
    workspace: str, canonical: Dict[str, Any], plugin_rel: str = "./plugin"
) -> Tuple[List[Artifact], List[Skip]]:
    """Marketplace catalogs at the repository root.

    The repository *is* the marketplace: a single-plugin catalog today, with room
    for optional add-on plugins later without restructuring anything. `source` is
    written explicitly rather than via `metadata.pluginRoot` so the two client
    catalogs stay byte-comparable.
    """
    source = "plugin/plugin.json"
    name = MARKETPLACE_NAME

    skips: List[Skip] = []
    if name in CLAUDE_RESERVED_MARKETPLACE_NAMES:
        raise BearingError(
            "marketplace name %r is reserved for official Anthropic use and would load as "
            "an untrusted source" % name
        )

    entry: Dict[str, Any] = {
        "name": canonical["name"],
        "source": plugin_rel,
        "description": canonical.get("description", ""),
    }
    for key in ("version", "author", "homepage", "repository", "license", "keywords"):
        if key in canonical:
            entry[key] = canonical[key]
    entry["category"] = "engineering-governance"
    entry["tags"] = ["adr", "decisions", "architecture", "legacy"]

    catalog: Dict[str, Any] = {
        "name": name,
        "owner": {
            "name": (canonical.get("author") or {}).get("name", "BEARING maintainers"),
        },
        "metadata": {
            "description": "The BEARING decision system.",
            "version": canonical.get("version", "0.0.0"),
        },
        "plugins": [entry],
    }

    artifacts: List[Artifact] = []
    for directory, what in (
        (
            ".cursor-plugin",
            "Cursor reads a marketplace catalog from `.cursor-plugin/marketplace.json` at the "
            "repository root. Register it with `cursor-agent plugin marketplace add <git-url>`.",
        ),
        (
            ".claude-plugin",
            "Claude Code reads a marketplace catalog from `.claude-plugin/marketplace.json` at "
            "the repository root. Register it with `/plugin marketplace add <owner>/<repo>`.",
        ),
    ):
        body = dict(catalog)
        # Cursor-only marketplace fields (display title + bundled MCP). Keep Claude's
        # catalog free of unknown keys.
        if directory == ".cursor-plugin":
            cursor_entry = dict(entry)
            cursor_entry["displayName"] = PRODUCT_DISPLAY_NAME
            cursor_entry["mcpServers"] = "./mcp.json"
            cursor_entry["skills"] = CURSOR_SKILLS_PATH
            cursor_entry["hooks"] = "./hooks/cursor.json"
            body = dict(catalog)
            body["plugins"] = [cursor_entry]
        artifacts.append(
            Artifact(
                path=os.path.join(workspace, directory, "marketplace.json"),
                content=dump_json(body),
                source=source,
                kind="marketplace",
                target=directory.strip("."),
                scope="package",
            )
        )
        artifacts.append(
            Artifact(
                path=os.path.join(workspace, directory, "GENERATED.md"),
                content=generated_dir_notice(what),
                source=source,
                kind="marketplace",
                target=directory.strip("."),
                scope="package",
            )
        )

    # Codex distributes through the shared ChatGPT/Codex plugin directory rather
    # than a git-hosted catalog, so there is no third marketplace file to emit.
    skips.append(
        Skip(
            "marketplace",
            "codex",
            "Codex distributes plugins through the shared ChatGPT plugin directory and "
            "defines no git-hosted marketplace manifest; .codex-plugin/plugin.json is "
            "sufficient for installation",
            "package",
        )
    )

    return artifacts, skips


def codex_skill_metadata(plugin_root: str) -> List[Artifact]:
    """Per-skill `agents/openai.yaml` for Codex.

    Carries display metadata and, more importantly, invocation policy. The
    onboarding skill sets `allow_implicit_invocation: false` because it must be
    run deliberately once per repository -- a skill that tags and branches a
    repository is not something an agent should decide to start on its own.
    """
    out: List[Artifact] = []
    for skill_name in PLUGIN_SKILL_NAMES:
        skill_dir = os.path.join(plugin_root, "skills", skill_name)
        skill_file = os.path.join(skill_dir, "SKILL.md")
        text = read_text(skill_file)
        if text is None:
            continue
        front, _ = parse_frontmatter(text)
        description = str(front.get("description", "")).strip()
        short = description.split(". ")[0].rstrip(".")
        implicit = skill_name != "decision-onboarding"

        lines = [
            "interface:",
            '  display_name: "%s"' % _display_name(skill_name),
            '  short_description: "%s"' % short.replace('"', "'"),
            "policy:",
            "  allow_implicit_invocation: %s" % ("true" if implicit else "false"),
        ]
        if not implicit:
            lines.append(
                "  # Onboarding tags a baseline commit and creates a branch. That is a"
            )
            lines.append(
                "  # deliberate, once-per-repository act, not something to infer from a prompt."
            )

        out.append(
            Artifact(
                path=os.path.join(skill_dir, "agents", "openai.yaml"),
                content="\n".join(lines) + "\n",
                source="plugin/skills/%s/SKILL.md" % skill_name,
                kind="manifest",
                target="codex",
                scope="package",
            )
        )
    return out


def _display_name(skill_name: str) -> str:
    return " ".join(part.capitalize() for part in skill_name.split("-"))


def mcp_manifest(plugin_root: str) -> List[Artifact]:
    """Ship MCP with the plugin so marketplace install surfaces disposition tools.

    Uses `${PLUGIN_ROOT}` (Cursor/Agent Plugins built-in), not `${workspaceFolder}`.
    The latter only applies to a project's `.cursor/mcp.json` and is the wrong
    variable for plugin-bundled servers — it is what made MCP feel "broken"
    after a plugin-only install.
    """
    payload = {
        "mcpServers": {
            PRODUCT_DISPLAY_NAME: {
                "command": "python3",
                "args": ["hooks/run_mcp.py"],
                "cwd": "${PLUGIN_ROOT}",
            }
        }
    }
    return [
        Artifact(
            path=os.path.join(plugin_root, "mcp.json"),
            content=dump_json(payload),
            source="plugin/src/bearing/manifests.py",
            kind="manifest",
            target="cursor",
            scope="package",
        )
    ]


def hooks_manifests(plugin_root: str) -> List[Artifact]:
    """The `workspaceOpen` hook backing `scope: "ephemeral"` projections.

    Cursor's `workspaceOpen` hook may return `{"pluginPaths": [...]}` to load
    plugins for the workspace that just opened. That is what makes ephemeral
    projection possible: adapters are rendered to a temp directory at session
    start and nothing is ever written into the working tree -- which is how you
    evaluate BEARING against a baseline you are not allowed to modify.
    """
    cursor_payload = {
        "version": 1,
        "hooks": {
            "workspaceOpen": [
                {
                    "command": "python3 hooks/render_ephemeral.py",
                    "timeout": 30,
                }
            ]
        },
    }
    claude_payload = {
        "description": "Inject matching Accepted Contracts before governed file mutations.",
        "hooks": {
            "UserPromptSubmit": [
                {
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/context_injection.py"',
                            "timeout": 30,
                        }
                    ]
                }
            ],
            "PreToolUse": [
                {
                    "matcher": "Read|Edit|Write",
                    "hooks": [
                        {
                            "type": "command",
                            "command": 'python3 "${CLAUDE_PLUGIN_ROOT}/hooks/context_injection.py"',
                            "timeout": 30,
                        }
                    ],
                }
            ]
        },
    }
    return [
        Artifact(
            path=os.path.join(plugin_root, "hooks", "cursor.json"),
            content=dump_json(cursor_payload),
            source="plugin/src/bearing/manifests.py",
            kind="manifest",
            target="cursor",
            scope="package",
        ),
        Artifact(
            path=os.path.join(plugin_root, "hooks", "hooks.json"),
            content=dump_json(claude_payload),
            source="plugin/src/bearing/manifests.py",
            kind="manifest",
            target="claude",
            scope="package",
        ),
    ]


def all_package_artifacts(
    workspace: str, plugin_root: str
) -> Tuple[List[Artifact], List[Skip]]:
    canonical = load_canonical(plugin_root)
    artifacts: List[Artifact] = []
    artifacts.extend(plugin_manifests(plugin_root, canonical))
    artifacts.extend(codex_skill_metadata(plugin_root))
    artifacts.extend(hooks_manifests(plugin_root))
    artifacts.extend(mcp_manifest(plugin_root))
    schema_source = os.path.join(plugin_root, "src", "bearing", "data", "config.schema.json")
    schema_content = read_text(schema_source)
    if schema_content is None:
        raise BearingError("missing packaged configuration schema at %s" % schema_source)
    artifacts.extend(
        [
            Artifact(
                path=os.path.join(workspace, "schemas", "config-1.json"),
                content=schema_content,
                source="plugin/src/bearing/data/config.schema.json",
                kind="schema",
                target="public",
                scope="package",
            ),
            Artifact(
                path=os.path.join(workspace, "schemas", "GENERATED.md"),
                content=generated_dir_notice(
                    "The public configuration schema is generated from the schema shipped "
                    "inside the BEARING Python package."
                ),
                source="plugin/src/bearing/data/config.schema.json",
                kind="schema",
                target="public",
                scope="package",
            ),
        ]
    )
    market, skips = marketplace_manifests(workspace, canonical)
    artifacts.extend(market)
    artifacts.append(
        Artifact(
            path=os.path.join(plugin_root, "hooks", "GENERATED.md"),
            content=generated_dir_notice(
                "Claude reads `hooks/hooks.json` by convention; Cursor's manifest points at "
                "`hooks/cursor.json`. Their incompatible schemas are generated separately."
            ),
            source="plugin/src/bearing/manifests.py",
            kind="manifest",
            target="cursor",
            scope="package",
        )
    )
    from .compatibility import build_summary

    overrides = {artifact.path: artifact.content for artifact in artifacts}
    summary = build_summary(workspace, overrides=overrides)
    artifacts.append(
        Artifact(
            path=os.path.join(plugin_root, "runtime-compatibility.json"),
            content=dump_json(summary),
            source="conformance/evidence/*.json",
            kind="compatibility",
            target="all",
            scope="package",
        )
    )
    matrix = [
        "# Runtime support",
        "",
        "Support is qualified by Tier 4 evidence for behaviorally relevant artifacts.",
        "",
        "| Runtime | Discovery | Evidence | Verified range |",
        "| --- | --- | --- | --- |",
    ]
    for entry in summary["runtimes"]:
        evidence = entry.get("evidence") or {}
        verified = "verified" if evidence else "unverified"
        version_range = (
            "%s through %s"
            % (evidence.get("runtime_version_min"), evidence.get("runtime_version_max"))
            if evidence
            else "—"
        )
        matrix.append(
            "| %s | %s | %s | %s |"
            % (entry["runtime"], entry["discovery_mode"], verified, version_range)
        )
    matrix += [
        "",
        "Documentation changes do not invalidate this evidence. Adapter, hook, manifest, ",
        "schema, renderer, or compatibility-API changes invalidate only affected runtimes.",
        "",
    ]
    artifacts.append(
        Artifact(
            path=os.path.join(workspace, "docs", "runtime-support.md"),
            content="\n".join(matrix),
            source="conformance/evidence/*.json",
            kind="compatibility",
            target="all",
            scope="package",
        )
    )
    return artifacts, skips


def version_consistency_errors(plugin_root: str, package_version: str) -> List[str]:
    """`plugin.json` and `__init__.__version__` must agree.

    Two version numbers that can disagree is exactly the second-source-of-truth
    problem this architecture exists to prevent, so it is checked rather than
    trusted.
    """
    canonical = read_json(os.path.join(plugin_root, "plugin.json"), {}) or {}
    declared = canonical.get("version")
    if declared and declared != package_version:
        return [
            "plugin/plugin.json declares version %r but the bearing package reports %r; "
            "these must match" % (declared, package_version)
        ]
    return []
