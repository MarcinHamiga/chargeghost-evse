#!/usr/bin/env bash
# bump-version.sh — update version across all project files
# Usage: ./scripts/bump-version.sh 0.5.0
set -euo pipefail

if [[ $# -ne 1 ]]; then
	echo "Usage: $0 <version>  (e.g. 0.5.0)" >&2
	exit 1
fi

VERSION="${1#v}"   # strip leading 'v' if provided
VTAG="v${VERSION}"

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
PYPROJECT="$ROOT/pyproject.toml"
INIT="$ROOT/src/chargeghost_evse/__init__.py"
SPEC="$ROOT/assets/build/chargeghost-evse.spec"

# Validate semver format
if ! [[ "$VERSION" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
	echo "Error: version must be MAJOR.MINOR.PATCH (got '$VERSION')" >&2
	exit 1
fi

# Detect current version from pyproject.toml
CURRENT=$(grep '^version = ' "$PYPROJECT" | sed -E 's/^version = "v?([^"]*)"/\1/')

echo "Bumping $CURRENT → $VERSION"

# pyproject.toml:  version = "v0.4.1"
sed -i '' -E "s/^version = \"v?[^\"]*\"/version = \"${VTAG}\"/" "$PYPROJECT"

# __init__.py:  __version__ = "0.4.1"
sed -i '' -E "s/^__version__ = \"[^\"]*\"/__version__ = \"${VERSION}\"/" "$INIT"

# .spec:  version="v0.4.1"
sed -i '' -E "s/version=\"v?[^\"]*\"/version=\"${VTAG}\"/" "$SPEC"

echo "Updated:"
echo "  $PYPROJECT"
echo "  $INIT"
echo "  $SPEC"
