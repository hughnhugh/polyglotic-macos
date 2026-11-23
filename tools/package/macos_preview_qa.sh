#!/usr/bin/env bash
# Build a local review copy in the disposable, scanned checkout.
set -euo pipefail
[[ "$(uname -s)" == Darwin && "${GITHUB_ACTIONS:-}" == true && "${RUNNER_ENVIRONMENT:-}" == github-hosted ]]
out="out/${1:?evidence folder name}"
mkdir -p "$out"
uv run --no-sync python -m tools.package.macos_preview_qa "$out"
uv run --no-sync python -m tools.dictionaries.build
uv sync --locked --no-default-groups --group package
uv run --no-sync python -m tools.package.build v0.1.10 --channel macos-arm64-alpha
cp build/package/{summary,check-install}.json "$out/"
app="dist/Polyglotic Preview.app"
mv dist/Polyglotic.app "$app"
test "$(/usr/libexec/PlistBuddy -c 'Print CFBundleIdentifier' "$app/Contents/Info.plist")" == io.polyglotic.desktop.preview
test "$(/usr/libexec/PlistBuddy -c 'Print CFBundleDisplayName' "$app/Contents/Info.plist")" == 'Polyglotic Preview'
codesign --verify --deep --strict "$app"
zip="$out/Polyglotic-Preview-macOS-arm64.zip"
ditto -c -k --sequesterRsrc --keepParent "$app" "$zip"
shasum -a 256 "$zip" > "$out/SHA256SUMS"
extracted=$(mktemp -d)
ditto -x -k "$zip" "$extracted"
copy="$extracted/Polyglotic Preview.app"
codesign --verify --deep --strict "$copy"
uv run --with pyobjc-framework-Quartz==13.0 python -m tools.macos_bundle_home "$copy" "$out/home"
