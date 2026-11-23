# Run the desktop QA on GitHub's Macs

From a desktop worktree, use the HQ remote test launcher. It scans and filters the snapshot before dispatching the existing workflow on the public spike. The macOS job uses an Apple silicon macOS 15 GUI session. Each interactive job gets one machine and one process. The commands below use PowerShell and assume the HQ scripts directory is in `$HqScripts`.

```powershell
python -I "$HqScripts/remote_test.py" . --os macos --shards 1 --processes 1 --each 'uv run --with pyobjc-framework-Quartz==13.0 python -m tools.macos_window_qa out/{}' --items windows
python -I "$HqScripts/remote_test.py" . --os macos --shards 1 --processes 1 --each 'uv run --no-sync python -m tools.macos_sweep_evidence out/{}' --items settings
python -I "$HqScripts/remote_test.py" . --os macos --shards 2 --processes 1 --each 'uv run --no-sync python -m tools.macos_ui_lab {}' --items en,zh_CN
python -I "$HqScripts/remote_test.py" . --os macos --shards 1 --processes 1 --each 'uv run --no-sync python -m tools.macos_full_screen_checks out/{}.json' --items full-screen
python -I "$HqScripts/remote_test.py" . --os macos --shards 1 --processes 1 --each 'uv run --no-sync python -m tools.macos_audio_qa out/{}' --items audio
python -I "$HqScripts/remote_test.py" . --os macos --shards 1 --processes 1 --each 'uv run --with pyobjc-framework-Quartz==13.0 python -m tools.macos_audio_permission_qa out/{}' --items permission
python -I "$HqScripts/remote_test.py" . --os macos --shards 1 --processes 1 --each 'uv run --no-sync python -m tools.capture_choice_qa out/{}' --items capture-choice
python -I "$HqScripts/remote_test.py" . --os windows --shards 1 --processes 1 --each 'uv run --no-sync python -m tools.capture_choice_qa out/{}' --items capture-choice
python -I "$HqScripts/remote_test.py" . --os macos --shards 1 --processes 1 --each 'bash tools/package/macos_qa.sh {}' --items bundle
python -I "$HqScripts/remote_test.py" . --os macos --shards 1 --processes 1 --each 'bash tools/package/macos_preview_qa.sh {}' --items preview
```

The launcher prints the Actions link and downloads each artifact to `build/remote-test/<run-id>/junit-<shard>/` before removing the temporary branch and hosted artifacts. Keep the downloaded evidence with the review. The pytest summary counts scenarios. Read the per-step results to see what each scenario established.

## Window checks

The real desktop entry point opens Cocoa windows, with a loopback server, sample dictionaries, a synthetic beta account and replay audio. The harness sends system mouse events. Programmatic geometry positions a window before each trial. Only the Quartz drag changes its geometry during the measurement. The main and transcript windows have native frames. Caption windows handle their own drags. Tests use logical screen points, record the screen size, and check all four frame coordinates to a tolerance of two points.

Open `windows/steps.json`. Each row names the app's widget grab and a JPEG of the hosted desktop, the expected behavior, and the observed geometry. A missing picture fails the check. Caption and joined window drags also check the geometry the app intends to save. Full-width inward drags cover the case where the minimum size leaves no room to shrink. The menu-bar journey checks AppKit visibility, minimization, focus, active Space and full-screen state with no click. Inspect the desktop picture for occlusion and clipping. Other steps verify the email challenge and code with a stand-in, inspect missing glyphs and selected faces for each caption script, and read the exact F8 and dictation text from a temporary TextEdit document. The permission scenarios feed denials to the interface. The native audio probe uses the runner's existing permissions.

For a shorter window run, pass `geometry`, `status`, or `anki` after the output directory. The cursor check samples the WindowServer cursor image while the app is active and checks a visible directional handle while Finder owns the pointer. The audio-permission scenario plays a generated clip, leaves the native recording permission denied, opens the recovery pane and saves content-free tap counters. The capture-choice scenario measures applied source plans and listening sessions during app enumeration and deliberate source changes.

The manual `Mac desktop QA` workflow offers `macos-15` and `macos-26` on GitHub-hosted Apple silicon. Choose a runner and one scenario. A current TCC grant is required to establish positive system capture. Record the OS version, the denial or grant, and the actual measurements with the result.

The UI lab runs each state in a fresh Cocoa process. A state that throws, times out, or fails its visual checks is recorded in `ui-lab/<language>/states.json`. Each completed state has its own PNG and detailed JSON. On Cocoa the sign-out question uses a native alert. The runner photographs that alert, checks both localized AppKit buttons, activates Cancel and verifies the result. The two slide-animation states explicitly use the motion-enabled preference because the hosted Mac enables Reduce Motion. Compare an English picture with the corresponding Windows picture in `tools/ui_lab/goldens/`. Timing budgets and pixel differences across operating systems are separate from missing controls or illegible text.

The bundle job uses the packaging build and a local two-version update feed on the disposable runner. It downloads the dictionaries from their pinned sources, signs the build ad hoc, runs the install and login-item checks, and rehearses an update. The evidence contains reports. The separate preview command returns an ad-hoc signed `Polyglotic Preview.app` in a zip, its SHA-256, the preview bundle identity and window measurements from launching the extracted copy. Its Keychain service, data, cache and instance lock are separate. Application updates are disabled for the preview. The package script runs only in a disposable hosted checkout.

