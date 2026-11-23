# 0289 Declare tunables beside their readers and resolve them at startup

2026-11-21. Project 597, HQ decision 258.

Caption reading times and card depth depend on the learner and material. Each
declaration carries the shipped value, unit, bounds, source and when it applies.
Use `.value` when making the decision. Derived sizes and counts follow the same
snapshot. The normal launch reads `tunables.toml` in the selected data folder
or the file named by `--tunables`. The file can contain just the differences.

```toml
[dwell]
read_least = 1.2
[cards]
depth_scales = [1.0, 0.92, 0.84]
```

Precedence increases from shipped to cohort, local file and the learner's
changed settings. The cohort input is empty until a server delivers it.
Registration, ranges and layer resolution are plain Python. Reading rules
check a candidate before the registry publishes it. Unknown and individually
invalid fields are skipped with a warning. A cross-value refusal discards
the whole candidate layer. No file loads on the common path besides the
probe for the override. The TOML parser is imported only when the file opens.

Run `python -m tools.tunables list` for names and units, `check FILE` before
a trial and `promote FILE` to edit shipped declarations in a checkout for
review. The latter two reject files with warnings. Preset mode names in TOML
are the current product names. The app translates them to its historic settings
keys. Video's inherited shipped Steady on the 583 branch remains available
until project 587 updates it. Explicit override files follow decision 255.

If reviewers find declarations harder to maintain than one versioned defaults
file, generate that file from the registry, read it at startup and retain
typed handles at the call sites. Removing the override file restores shipped
defaults on the next launch wherever the learner has no choice of their own.
