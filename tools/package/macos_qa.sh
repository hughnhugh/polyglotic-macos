#!/usr/bin/env bash
# Rehearse the bundle on the disposable Mac. Return only check results.
set -euo pipefail
[[ "$(uname -s)" == Darwin && "${GITHUB_ACTIONS:-}" == true && "${RUNNER_ENVIRONMENT:-}" == github-hosted ]]
out="out/${1:?evidence folder name}"
mkdir -p "$out"
uv run --no-sync python -m tools.dictionaries.build
uv sync --locked --no-default-groups --group package
status=0
uv run --no-sync python -m tools.package.build v0.0.1 --channel macos-arm64-alpha || status=$?
for file in summary.json check-install.json; do
  if [[ -f "build/package/$file" ]]; then cp "build/package/$file" "$out/"; fi
done
app=dist/Polyglotic.app
[[ -x "$app/Contents/MacOS/Polyglotic" ]]
uv run --no-sync python -m tools.macos_parity_checks "$out/parity" --app "$app" || status=1
uv run --with pyobjc-framework-Quartz==13.0 python -m tools.macos_bundle_home "$app" "$out/home" || status=1
dotnet tool restore
bash tools/package/macos_update_rehearsal.sh "$app" "$out/updates" || status=1
exit "$status"
