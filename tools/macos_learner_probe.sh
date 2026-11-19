#!/usr/bin/env bash
# polyglotic-hq 523: what GitHub's Mac has that a learner's doesn't (a probe,
# not for merging)
set -u
say() { echo; echo "== $*"; }
say machine; sw_vers; whoami; id
say gatekeeper; spctl --status 2>&1; csrutil status 2>&1
say pythons; ls -d /Library/Frameworks/Python.framework/Versions/* 2>&1; which -a python3 python3.12 python3.11 python3.13 2>&1
say homebrew; ls -d /opt/homebrew /usr/local/Homebrew /usr/local/Cellar 2>&1; ls /opt/homebrew/bin 2>/dev/null | wc -l; ls /usr/local/bin 2>/dev/null | wc -l; ls /usr/local/lib 2>/dev/null | head -30
say tools; which -a brew git clang xcrun cliclick jq gh dotnet node 2>&1; xcode-select -p 2>&1; ls -d /Applications/Xcode* /Library/Developer/* 2>&1
say uv; which -a uv; uv python list 2>&1 | head -20; uv run --no-sync python -c "import sys,ssl; print(sys.executable, sys.base_prefix, sys.version, ssl.OPENSSL_VERSION, ssl.get_default_verify_paths())"
say path; echo "$PATH" | tr ':' '\n'
say env; env | grep -iE 'DYLD|SSL|PYTHON|HOMEBREW|DEVELOPER|SDKROOT' | sed -E 's/=.*/=<set>/'
say users; dscl . list /Users | grep -v '^_'
say "a fresh account"
pw="$(openssl rand -hex 12)"
sudo sysadminctl -addUser learner523 -fullName "Learner 523" -password "$pw" 2>&1 | tail -3
id learner523 2>&1
sudo -u learner523 -H bash -c 'echo "home $HOME"; ls -la "$HOME" | head; ls "$HOME/Library" 2>&1 | head; security list-keychains 2>&1' 2>&1 | head -30
say "a tiny quarantined app opened from Downloads"
t="$(mktemp -d)"; app="$t/Probe523.app"; mkdir -p "$app/Contents/MacOS"
cat > "$app/Contents/Info.plist" <<'EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleExecutable</key><string>probe</string>
<key>CFBundleIdentifier</key><string>io.polyglotic.probe523</string>
<key>CFBundleName</key><string>Probe523</string>
<key>CFBundlePackageType</key><string>APPL</string>
</dict></plist>
EOF
printf '#!/bin/sh\necho "$0" > /tmp/probe523-ran.txt\n' > "$app/Contents/MacOS/probe"; chmod +x "$app/Contents/MacOS/probe"
codesign -s - --force --deep "$app" 2>&1
(cd "$t" && ditto -c -k --keepParent Probe523.app Probe523.zip)
mkdir -p ~/Downloads; cp "$t/Probe523.zip" ~/Downloads/
qtn="0083;$(printf '%x' "$(date +%s)");Safari;$(uuidgen)"
xattr -w com.apple.quarantine "$qtn" ~/Downloads/Probe523.zip
xattr -p com.apple.quarantine ~/Downloads/Probe523.zip
(cd ~/Downloads && ditto -x -k Probe523.zip . )
echo "after ditto -x: $(xattr -p com.apple.quarantine ~/Downloads/Probe523.app 2>&1)"
rm -rf ~/Downloads/Probe523.app
open -W -a "Archive Utility" ~/Downloads/Probe523.zip 2>&1 & au=$!; sleep 8; kill $au 2>/dev/null
ls -la ~/Downloads
echo "after Archive Utility: $(xattr -p com.apple.quarantine ~/Downloads/Probe523.app 2>&1)"
if [ ! -d ~/Downloads/Probe523.app ]; then (cd ~/Downloads && ditto -x -k Probe523.zip .); xattr -r -w com.apple.quarantine "$qtn" ~/Downloads/Probe523.app; fi
spctl -a -vv ~/Downloads/Probe523.app 2>&1
rm -f /tmp/probe523-ran.txt
open ~/Downloads/Probe523.app 2>&1; sleep 5
echo "ran from: $(cat /tmp/probe523-ran.txt 2>&1)"
xattr -p com.apple.quarantine ~/Downloads/Probe523.app 2>&1
log show --last 1m --style compact --predicate 'process == "syspolicyd" OR process == "CoreServicesUIAgent"' 2>/dev/null | tail -15
osascript -e 'tell application "System Events" to get name of every process whose background only is false' 2>&1
say "spctl --add"
sudo spctl --add --label Probe523 ~/Downloads/Probe523.app 2>&1; spctl -a -vv ~/Downloads/Probe523.app 2>&1
rm -f /tmp/probe523-ran.txt; open ~/Downloads/Probe523.app 2>&1; sleep 5; echo "ran from: $(cat /tmp/probe523-ran.txt 2>&1)"
say "approved flag"
xattr -w com.apple.quarantine "00c3;$(printf '%x' "$(date +%s)");Safari;$(uuidgen)" ~/Downloads/Probe523.app
rm -f /tmp/probe523-ran.txt; open ~/Downloads/Probe523.app 2>&1; sleep 5; echo "ran from: $(cat /tmp/probe523-ran.txt 2>&1)"
say "the end"; sudo sysadminctl -deleteUser learner523 2>&1 | tail -1
exit 0
