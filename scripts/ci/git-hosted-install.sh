#!/usr/bin/env bash
#
# Tier 2 of the local-to-marketplace path: install BEARING the way a git-hosted
# marketplace does, then drive it against a repository it has never seen.
#
# A local-path install copies the working tree, so a file that exists on disk but
# is excluded from git still arrives. A git-hosted install resolves a ref, so
# anything ignored simply is not there -- a defect that only ever appears for
# other people. Cloning into an unrelated directory also breaks any `../`
# reference that happened to resolve inside the original checkout, which is the
# reference class Agent Plugins v1.0.0 section 4.1.3 requires clients to reject.
#
# Run from the repository root.

set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$repo_root"

# CI provides `python`; a developer's machine often only has `python3`.
PYTHON="${PYTHON:-$(command -v python || command -v python3)}"
if [ -z "$PYTHON" ]; then
  echo "FAIL: no python interpreter found on PATH." >&2
  exit 1
fi

install_root="$(mktemp -d)"
target="$(mktemp -d)"
trap 'chmod -R u+w "$install_root" 2>/dev/null || true; rm -rf "$install_root" "$target"' EXIT

# Prefer cloning the committed ref, which is exactly what a marketplace resolves.
# Before the first commit that is not yet possible, so fall back to staging the
# working tree in a scratch repository. The fallback still honours `.gitignore`,
# which is the property this tier is really checking -- an ignored file does not
# arrive on the other side of a git-hosted install.
if git -C "$repo_root" cat-file -e HEAD:plugin/plugin.json 2>/dev/null; then
  echo "==> Cloning this ref into a directory with no relationship to the checkout"
  git clone --quiet --depth 1 "file://$repo_root" "$install_root/marketplace"
else
  echo "==> plugin/plugin.json is not committed yet; staging the working tree instead"
  echo "    (.gitignore is still honoured, so an ignored file will still be caught)"
  origin="$install_root/origin"
  mkdir -p "$origin"
  # `git ls-files` cannot be used here because the files are untracked; a copy
  # plus `git add -A` reproduces the same exclusion rules.
  cp -R "$repo_root/plugin" "$origin/plugin"
  cp "$repo_root/.gitignore" "$origin/.gitignore"
  find "$origin" -name '__pycache__' -type d -prune -exec rm -rf {} +
  git -C "$origin" init --quiet
  git -C "$origin" config user.email "ci@example.invalid"
  git -C "$origin" config user.name "CI"
  git -C "$origin" add -A
  git -C "$origin" commit --quiet -m "working tree"
  git clone --quiet --depth 1 "file://$origin" "$install_root/marketplace"
fi

plugin="$install_root/marketplace/plugin"

for required in \
  "plugin.json" \
  "bin/bearing" \
  "bin/bearing-mcp" \
  "src/bearing/cli.py" \
  "src/bearing/data/config.default.json" \
  "src/bearing/data/templates/schemas/config.schema.json" \
  "src/bearing/data/pricing.default.json" \
  "skills/decision-recovery/SKILL.md" \
  "skills/decision-recovery/schemas/candidate.schema.json"
do
  if [ ! -f "$plugin/$required" ]; then
    echo "FAIL: $required did not survive the clone, so a git-hosted install ships without it." >&2
    exit 1
  fi
done

# A content digest of the whole plugin tree, so "did BEARING write inside its own
# installation" is answered by comparing bytes rather than by trusting mtimes.
# `__pycache__` is excluded because the interpreter writes it and that is the
# interpreter's business, not BEARING's.
plugin_digest() {
  find "$plugin" -type f -not -path '*__pycache__*' -not -name '*.pyc' -print0 \
    | LC_ALL=C sort -z \
    | xargs -0 shasum -a 256 2>/dev/null \
    | sed "s|$plugin/||"
}

plugin_digest > "$install_root/before.sha"

echo "==> Building a scratch repository to stand in for a user's project"
mkdir -p "$target/src/billing"
cat > "$target/src/billing/invoice.py" <<'PY'
def total(lines):
    return sum(line.amount for line in lines)
PY
git -C "$target" init --quiet
git -C "$target" config user.email "ci@example.invalid"
git -C "$target" config user.name "CI"
git -C "$target" add -A
git -C "$target" commit --quiet -m "initial"

export PYTHONPATH="$plugin/src"
export NO_COLOR=1
# Isolate operator config: a runner must not read, or create, a developer's
# user-scope settings.
export BEARING_HOME="$target/.bearing-home"
# Adapters into the working tree, because a runner has no user-scope agent
# directories and should not invent any.
export BEARING_PROJECTIONS_SUBAGENTS_SCOPE='"repo"'

cd "$target"

echo "==> bearing init"
"$PYTHON" -m bearing init --yes

echo "==> bearing doctor"
"$PYTHON" -m bearing doctor

echo "==> bearing render --check  (init rendered; a second pass must find no drift)"
"$PYTHON" -m bearing render --check

echo "==> bearing index"
"$PYTHON" -m bearing index

echo "==> bearing lint"
"$PYTHON" -m bearing lint

echo "==> Making the plugin tree read-only and re-running"
# The purity rule, enforced rather than asserted: if anything in BEARING writes
# inside its own installation -- a ledger, a transcript, an eval result -- these
# fail here rather than silently losing data on the next plugin update.
chmod -R a-w "$plugin"
"$PYTHON" -m bearing render --check
"$PYTHON" -m bearing index
"$PYTHON" -m bearing lint
"$PYTHON" -m bearing report
chmod -R u+w "$plugin"

echo "==> Confirming the plugin tree is byte-identical to what was installed"
plugin_digest > "$install_root/after.sha"
if ! diff -u "$install_root/before.sha" "$install_root/after.sha"; then
  echo "FAIL: the plugin tree changed while BEARING ran. A plugin that writes inside" >&2
  echo "      its own installation loses that data on the next update." >&2
  exit 1
fi

echo "==> bearing uninstall leaves decision content behind"
"$PYTHON" -m bearing uninstall
test -f "$target/docs/decisions/index.json" \
  || { echo "FAIL: uninstall removed the disclosure index." >&2; exit 1; }
test ! -e "$target/.cursor/agents/decision-archaeologist.md" \
  || { echo "FAIL: uninstall left a generated adapter behind." >&2; exit 1; }

echo "==> pip/setuptools install (site-packages layout, the pipx path)"
# InstalledCopyTest copies the plugin tree and puts src/ on PYTHONPATH, which is
# the marketplace-copy shape. `pipx install ./plugin` only places `bearing` on
# site-packages; plugin.json and skills/ must be bundled inside that package or
# `bearing doctor` fails even when the Cursor GUI plugin is installed.
site="$install_root/pip-site"
mkdir -p "$site"
if ! "$PYTHON" -m pip install --no-deps --quiet --target "$site" "$plugin"; then
  echo "FAIL: pip install of the plugin directory failed." >&2
  exit 1
fi
if [ ! -f "$site/bearing/plugin.json" ]; then
  echo "FAIL: pip install did not bundle plugin.json inside the bearing package." >&2
  exit 1
fi
if [ ! -f "$site/bearing/skills/decision-recovery/SKILL.md" ]; then
  echo "FAIL: pip install did not bundle Skills inside the bearing package." >&2
  exit 1
fi
PYTHONPATH="$site" "$PYTHON" -c "
from bearing.doctor import _plugin_check
check = _plugin_check()
if check.status != 'ok':
    raise SystemExit('plugin check: %s %s' % (check.status, check.detail))
print('PASS: pip-installed CLI resolves plugin at', check.detail)
"

echo
echo "PASS: git-hosted install is clean."
