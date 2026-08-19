"""Generated artifacts, and the lock file that keeps them honest.

@see ADR-0003 — every generated file is recorded; a skip is a recorded absence.

Every file BEARING generates passes through here, so three properties hold
uniformly rather than per-renderer:

1. **Determinism.** No timestamps, no absolute paths, no dict iteration order.
   Two runs on the same inputs produce byte-identical output, which is what
   makes `--check` a usable CI gate instead of a source of spurious failures.
2. **Attribution.** Every artifact names the canonical source it came from, in a
   header where the format allows comments and in the lock file always.
3. **Recorded absence.** A target that was deliberately not generated is written
   to the lock file as a skip with a reason. Without that, a missing adapter is
   ambiguous -- switched off on purpose, or silently broken? -- and the next
   person to look has to guess.
"""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Sequence, Tuple

from . import RENDERER_VERSION, __version__
from .util import BearingError, dump_json, read_json, read_text, sha256_text, write_text

# JSON has no comment syntax, so JSON artifacts carry their notice in a sibling
# GENERATED.md rather than inside the file. Injecting a marker key instead was
# rejected: a plugin manifest that a client might reject for an unknown field is
# not worth a cosmetic warning, and the lock file already carries attribution.
_COMMENT_STYLES = {
    ".md": ("<!-- ", " -->"),
    ".mdc": ("<!-- ", " -->"),
    ".markdown": ("<!-- ", " -->"),
    ".toml": ("# ", ""),
    ".yaml": ("# ", ""),
    ".yml": ("# ", ""),
    ".py": ("# ", ""),
    ".sh": ("# ", ""),
    ".cfg": ("# ", ""),
}

NOTICE = "DO NOT EDIT. Generated from %s by bearing %s. Run `bearing render` to update; edits here are overwritten and reported as drift by `bearing render --check`."


def notice_for(extension: str, source: str) -> Optional[str]:
    style = _COMMENT_STYLES.get(extension.lower())
    if style is None:
        return None
    open_token, close_token = style
    return "%s%s%s" % (open_token, NOTICE % (source, __version__), close_token)


class Artifact:
    """One generated file, with everything needed to attribute and verify it."""

    def __init__(
        self,
        path: str,
        content: str,
        source: str,
        kind: str,
        target: str,
        scope: str = "repo",
        frontmatter_aware: bool = False,
    ) -> None:
        self.path = os.path.abspath(path)
        self.source = source
        self.kind = kind
        self.target = target
        self.scope = scope
        self.content = self._decorate(content, frontmatter_aware)

    def _decorate(self, content: str, frontmatter_aware: bool) -> str:
        _, extension = os.path.splitext(self.path)
        notice = notice_for(extension, self.source)
        if notice is None:
            return content
        if frontmatter_aware and content.startswith("---"):
            # A markdown file consumed for its frontmatter must still begin with
            # the `---` fence, so the notice goes immediately after the closing
            # fence rather than above the opening one.
            lines = content.split("\n")
            for index in range(1, len(lines)):
                if lines[index].strip() == "---":
                    head = lines[: index + 1]
                    tail = lines[index + 1:]
                    return "\n".join(head + ["", notice] + tail)
        return "%s\n\n%s" % (notice, content)

    @property
    def sha256(self) -> str:
        return sha256_text(self.content)

    def lock_path(self, workspace: str) -> str:
        """A machine-independent path for the lock file.

        User-scope artifacts land in the home directory, whose absolute path
        differs per machine and per CI runner. Recording them as `~/...` keeps
        the committed lock file identical for everyone.

        Workspace containment is tested first, because a workspace checked out
        somewhere under `$HOME` would otherwise have all of its repo-scoped
        artifacts recorded home-relative -- which is both wrong and unstable.
        """
        workspace = os.path.abspath(workspace)
        if self.path == workspace or self.path.startswith(workspace + os.sep):
            return os.path.relpath(self.path, workspace).replace(os.sep, "/")
        home = os.path.abspath(os.path.expanduser("~"))
        if self.path.startswith(home + os.sep):
            return "~/" + os.path.relpath(self.path, home).replace(os.sep, "/")
        return self.path.replace(os.sep, "/")


class Skip:
    """A target that was deliberately not generated."""

    def __init__(self, kind: str, target: str, reason: str) -> None:
        self.kind = kind
        self.target = target
        self.reason = reason

    def as_dict(self) -> Dict[str, str]:
        return {"kind": self.kind, "target": self.target, "reason": self.reason}


class ApplyResult:
    def __init__(self) -> None:
        self.written: List[str] = []
        self.unchanged: List[str] = []
        self.drifted: List[Tuple[str, str]] = []
        self.missing: List[str] = []
        self.orphaned: List[str] = []

    @property
    def clean(self) -> bool:
        return not self.drifted and not self.missing and not self.orphaned


def apply(
    artifacts: Sequence[Artifact],
    workspace: str,
    check: bool = False,
    previous_lock: Optional[Dict] = None,
) -> ApplyResult:
    """Write artifacts, or in check mode report what differs without writing."""
    result = ApplyResult()
    expected = {artifact.lock_path(workspace) for artifact in artifacts}

    for artifact in artifacts:
        key = artifact.lock_path(workspace)
        current = read_text(artifact.path)
        if check:
            if current is None:
                result.missing.append(key)
            elif current != artifact.content:
                result.drifted.append((key, _describe_drift(current, artifact.content)))
            else:
                result.unchanged.append(key)
            continue
        try:
            if write_text(artifact.path, artifact.content):
                result.written.append(key)
            else:
                result.unchanged.append(key)
        except (OSError, PermissionError) as error:
            alternatives = {
                "repo": "'user' (written to your home directory) or 'ephemeral' (a temp "
                "directory, nothing committed)",
                "user": "'repo' (committed into the workspace) or 'ephemeral' (a temp "
                "directory, nothing committed)",
                "ephemeral": "'repo' or 'user'",
                "package": "n/a -- this is a packaging artifact, not a projection",
            }
            raise BearingError(
                "cannot write %s: %s\n"
                "  This is a %r-scope %s projection. Either grant write access to that "
                "location, or set projections.%s.scope to %s."
                % (
                    artifact.path,
                    error,
                    artifact.scope,
                    artifact.kind,
                    artifact.kind,
                    alternatives.get(artifact.scope, "another scope"),
                )
            )

    # An artifact recorded in the lock but no longer generated is an orphan: the
    # config that produced it changed, and a stale adapter left on disk is
    # exactly the "second source of truth" the architecture forbids.
    for entry in (previous_lock or {}).get("artifacts", []):
        key = entry.get("path")
        if key and key not in expected:
            absolute = _absolute(key, workspace)
            if os.path.isfile(absolute):
                result.orphaned.append(key)
                if not check:
                    os.remove(absolute)

    return result


def _absolute(lock_path: str, workspace: str) -> str:
    if lock_path.startswith("~/"):
        return os.path.join(os.path.expanduser("~"), lock_path[2:])
    return os.path.join(workspace, lock_path)


def _describe_drift(current: str, expected: str) -> str:
    current_lines = current.split("\n")
    expected_lines = expected.split("\n")
    for index in range(max(len(current_lines), len(expected_lines))):
        found = current_lines[index] if index < len(current_lines) else "<end of file>"
        want = expected_lines[index] if index < len(expected_lines) else "<end of file>"
        if found != want:
            return "line %d: found %r, expected %r" % (index + 1, found[:60], want[:60])
    return "content differs"


def build_lock(
    artifacts: Sequence[Artifact], skips: Sequence[Skip], workspace: str
) -> Dict:
    """The lock file. Deliberately timestamp-free so it is byte-stable."""
    return {
        "bearing_version": __version__,
        "renderer_version": RENDERER_VERSION,
        "artifacts": sorted(
            (
                {
                    "path": artifact.lock_path(workspace),
                    "source": artifact.source,
                    "sha256": artifact.sha256,
                    "kind": artifact.kind,
                    "target": artifact.target,
                    "scope": artifact.scope,
                }
                for artifact in artifacts
            ),
            key=lambda entry: entry["path"],
        ),
        "skipped": sorted(
            (skip.as_dict() for skip in skips),
            key=lambda entry: (entry["kind"], entry["target"]),
        ),
    }


def read_lock(path: str) -> Optional[Dict]:
    return read_json(path)


def write_lock(path: str, lock: Dict) -> bool:
    return write_text(path, dump_json(lock))


def generated_dir_notice(what: str, command: str = "bearing package") -> str:
    """Sibling notice for directories of JSON artifacts, which cannot self-document."""
    return (
        "# Generated directory — do not edit\n\n"
        "Every file here is generated from `plugin/plugin.json` by `%s`.\n\n"
        "%s\n\n"
        "JSON has no comment syntax, so the do-not-edit notice lives here rather than inside "
        "the files themselves. Injecting a marker key was rejected: a plugin manifest that a "
        "client might reject for an unknown top-level field is not worth a cosmetic warning, "
        "and `.bearing/projections.lock.json` already records the hash and source of every "
        "generated file.\n\n"
        "Change `plugin/plugin.json` and re-run `%s`. `%s --check` fails CI on drift.\n"
        % (command, what, command, command)
    )
