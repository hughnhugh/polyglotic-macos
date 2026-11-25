# 838 sidebar icon visual review

Rework 5 fixes the two findings exposed by the new sidebar-specific states in
the actual widgets rather than suppressing either gate:

- Home's source names and translated row actions wrap at the 760 x 520 floor;
  the page column is allowed to shrink to its viewport, so it does not create a
  horizontal scrollbar in longer translations.
- Settings' live caption preview uses 110% text (the preview-only tunable,
  range 100-110%, chosen so its smallest real ink is 12 px instead of 11 px).

The native-Windows goldens to regenerate and approve are:

- `ui_next.sidebar_narrow`
- `ui_next.sidebar_selected_settings`
- `ui_next.w4_settings`
- `ui_next.w4_settings_minimum`

The latter two share the corrected live preview. The other 104 sidebar-review
states retain their approved layout and typography.
