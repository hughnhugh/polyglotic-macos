# Brief 858 withheld-golden evidence

## Reproduction

- Base: `10a7012ae028d576695ba844a198e29e2c9df9e4` (the second parent merged into the reviewed head).
- Reviewed head before this rework: `e3d7bf2d23a4bd1441f0d0dc2fbf7550a81305f3`.
- Command, run once in a detached base worktree and once in the 858 worktree: `uv run python -m tools.ui_lab --checks-only --at-normal --out <unique-output>`.
- Both captures used this Linux process, Qt/PySide environment, 100% DPI/text size, Normal app text, English, and each state’s own theme/input. The base used the head `.venv` directly because the installed `uv 0.7.22` cannot read base’s `uv >=0.13.5` requirement.
- This machine has none of the 547 Windows golden fonts (`fonts: 0 files, 4f53cda18c2baa0c`), so pixel counts establish same-machine base/head causes only. Windows golden approval remains with Claude.

## Results

“Checks match” means the final head has exactly the same code-check findings as base. Thus there are no new `clipped_text`, `type_scale`, `text_overlap`, or contrast findings in any of these states. The existing two contrast findings in `w4_settings_lab` occur in both captures.

| State | Base → final head checks | Same-machine visual result | Established cause |
|---|---|---:|---|
| `ui_next.known_map_beginner` | Checks match | resized | `#Card` is flat; the map legend uses the shared card component. |
| `ui_next.known_map_intermediate` | Checks match | resized | `#Card` is flat; the map legend uses the shared card component. |
| `ui_next.known_map_near_native` | Checks match | resized | `#Card` is flat; the map legend uses the shared card component. |
| `ui_next.w2_rail_popover` | Checks match | 144805 px | Shared button/segmented flat styling changes the transcript rail popover. |
| `ui_next.panel_speech` | Checks match | resized | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.panel_languages_this_window` | Checks match | resized | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.panel_look_rail` | Checks match | 448011 px | The branch intentionally renders this lab state with the transcript theme (`tools/ui_lab/panels.py`). |
| `ui_next.panel_change_everywhere` | Checks match | resized | Recommended tiles and their selected sample ring were flattened. |
| `ui_next.looks_tiles_dark` | Checks match | 35777 px | Recommended tiles and their selected sample ring were flattened. |
| `ui_next.looks_tiles_light` | Checks match | 88674 px | Recommended tiles and their selected sample ring were flattened. |
| `ui_next.w4_words_heard_heavy` | Checks match | 760585 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_learning` | Checks match | 732018 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_learning_both_open` | Checks match | 716583 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_learning_several` | Checks match | 729276 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_learning_window_unlimited` | Checks match | 730636 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_learning_window_custom` | Checks match | 728730 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_learning_pack_offer` | Checks match | 713144 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_learning_pack_none_yet` | Checks match | 723881 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_learning_pack_unchecked` | Checks match | 713634 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_learning_pack_downloading` | Checks match | 715354 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_learning_pack_failed` | Checks match | 714106 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_learning_pack_installed` | Checks match | 726898 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_learning_pack_offer_recorded` | Checks match | 713172 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_learning_pack_recorded` | Checks match | 715448 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_learning_built_in_recorded` | Checks match | 715457 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_settings` | Checks match | 663726 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_settings_speech` | Checks match | 729601 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_settings_app_scrolled` | Checks match | 743052 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_settings_minimum` | Checks match | 594291 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.w4_settings_lab` | Checks match | 700706 px | Main-window cards, spacing, controls, or light content surface changed under U1. |
| `ui_next.first_run_consent_margin_light` | Checks match | 44828 px | Shared fill-only button styling reaches this dialog state; no state input changed. |
| `ui_next.first_run_consent_margin_dark` | Checks match | 44823 px | Shared fill-only button styling reaches this dialog state; no state input changed. |
| `ui_next.first_run_consent_glaze_light` | Checks match | 52863 px | Shared fill-only button styling reaches this dialog state; no state input changed. |
| `ui_next.first_run_consent_glaze_dark` | Checks match | 52841 px | Shared fill-only button styling reaches this dialog state; no state input changed. |
| `ui_next.first_run_consent_signal_light` | Checks match | 54096 px | Shared fill-only button styling reaches this dialog state; no state input changed. |
| `ui_next.first_run_consent_signal_dark` | Checks match | 54017 px | Shared fill-only button styling reaches this dialog state; no state input changed. |
| `ui_next.first_run_consent_tester` | Checks match | 44941 px | Shared fill-only button styling reaches this dialog state; no state input changed. |
| `ui_next.first_run_level_light` | Checks match | resized | Shared fill-only button styling reaches this dialog state; no state input changed. |
| `ui_next.first_run_level_dark` | Checks match | resized | Shared fill-only button styling reaches this dialog state; no state input changed. |
| `ui_next.first_run_code_light` | Checks match | resized | Shared fill-only button styling reaches this dialog state; no state input changed. |
| `ui_next.first_run_code_dark` | Checks match | resized | Shared fill-only button styling reaches this dialog state; no state input changed. |
| `ui_next.beta_sign_in` | Checks match | resized | Shared fill-only button styling reaches this dialog state; no state input changed. |
| `ui_next.beta_sign_in_mainland` | Checks match | resized | Shared fill-only button styling reaches this dialog state; no state input changed. |

## Fixes from the comparison

- The first head capture made selected segmented labels bold. That changed their metrics and produced the new clipping across Speech, Learning, Words, and Settings states. Selected segments now use fill and colour only.
- The App-scrolled text-overlap report was a detector false positive: the opaque pinned heading intentionally occludes the scrolled card description. The detector now excludes text inside that occluding container; a regression test retains ordinary overlap detection.
- The `known_map_*` pictures change because those main-window states render the shared `Card`; `w2_rail_popover` changes because it renders the shared flat controls. No state fixture or input changed.

## Rework 6: narrowed overlap detector

- The 43-state base/head inventory above remains the review inventory; no state
  input or golden was changed in this rework.
- The `PinnedCard` allowance now applies only when that card is actually stacked
  above text from another widget branch. Overlapping children in the same card
  and a neighboring control stacked above the card are checked normally.
- `test_text_hidden_by_an_opaque_pinned_heading_is_not_an_overlap` is the
  intentional-occlusion example. The paired
  `test_overlapping_children_of_the_same_pinned_card_are_found` and
  `test_control_raised_above_a_pinned_card_is_still_an_overlap` examples prove
  the two formerly hidden genuine cases; `test_text_over_text_is_found` keeps
  ordinary overlap detection covered.
- A fresh Linux checks-only lab of all states produced no `text_overlap` finding,
  including none in the 43 reviewed states. Thus narrowing the exception did
  not reveal a functional overlap regression. The run did report pre-existing
  check/design findings and host-sensitive timing overruns, plus unusable pixel
  comparisons because this host has zero of the 547 Windows golden fonts.
  Those are not caused by this detector-only change; Windows golden approval
  remains with Claude.
