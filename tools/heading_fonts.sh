#!/usr/bin/env bash
# How the themes' heading faces in src/polyglotic_desktop/ui/assets/fonts
# were made (polyglotic-hq project 098, decision 0029). Not part of the
# build: the outputs are committed. Run from anywhere, with uv:
#
#   bash tools/heading_fonts.sh OUT_DIR
#
# 1. Google Fonts' variable fonts and their OFL texts, from google/fonts at
#    a pinned commit, checked against the SHA-256s recorded below;
# 2. each fixed at weight 600 (the serifs at optical size 24: a 24 px page
#    title), with fontTools in uv's own throwaway environment;
# 3. cut to Latin: ASCII, Latin-1, Latin Extended-A and -B (pinyin's tone
#    marks), combining marks, Vietnamese, punctuation; no hinting.
# The results' SHA-256s are printed, to compare with the committed files.
set -euo pipefail

OUT=${1:?usage: heading_fonts.sh OUT_DIR}
COMMIT=24ddc1f324cac5d9f5aedca126d298f56e3f1640
FONTTOOLS="fonttools==4.60.1"
export SOURCE_DATE_EPOCH=1793923200  # the fonts' own dates (head.modified): 2026-11-06, so the output repeats
UNICODES="U+0020-007E,U+00A0-024F,U+0300-036F,U+1E00-1EFF,U+2000-206F,U+20AC,U+2122,U+2190-2193,U+2212"
mkdir -p "$OUT/src"

fetch() { # family-folder file sha256
  local name
  name=$(printf '%s' "$2" | sed 's/\[/%5B/g; s/\]/%5D/g')
  curl -sSfL -o "$OUT/src/$2" \
    "https://raw.githubusercontent.com/google/fonts/$COMMIT/ofl/$1/$name"
  echo "$3  $OUT/src/$2" | sha256sum -c --quiet -
}
fetch literata "Literata[opsz,wght].ttf" b41138c9373112f32abb589cc22e8674b06ed4048b0c513be922bdd26f274440
fetch sourceserif4 "SourceSerif4[opsz,wght].ttf" 97b2d4da6e3cb494b5a1e66ae176914d852ccabef49e0c02c0df25f3e39aca0b
fetch overpass "Overpass[wght].ttf" 970717df17a7f9911dee45f60695d05bfa9d745fa0a11fc5c348371fa21f0073

fonttools() { uvx --from "$FONTTOOLS" "$@"; }

# Literata's STAT names no 24 pt optical size, so fontTools can't name the
# instance itself: named here as it names the other two.
fonttools python -I -c '
import sys
from fontTools.ttLib import TTFont
from fontTools.varLib.instancer import instantiateVariableFont
font = instantiateVariableFont(TTFont(sys.argv[1]), {"wght": 600, "opsz": 24})
names = {1: "Literata SemiBold", 2: "Regular", 4: "Literata SemiBold",
         6: "Literata-SemiBold", 16: "Literata", 17: "SemiBold"}
for name_id, text in names.items():
    font["name"].setName(text, name_id, 3, 1, 0x409)
    font["name"].setName(text, name_id, 1, 0, 0)
font["OS/2"].usWeightClass = 600
font.save(sys.argv[2])
' "$OUT/src/Literata[opsz,wght].ttf" "$OUT/src/Literata-600.ttf"
fonttools fonttools varLib.instancer "$OUT/src/SourceSerif4[opsz,wght].ttf" \
  wght=600 opsz=24 --update-name-table -o "$OUT/src/SourceSerif4-600.ttf"
fonttools fonttools varLib.instancer "$OUT/src/Overpass[wght].ttf" \
  wght=600 --update-name-table -o "$OUT/src/Overpass-600.ttf"

for face in Literata SourceSerif4 Overpass; do
  fonttools pyftsubset "$OUT/src/$face-600.ttf" --unicodes="$UNICODES" \
    --no-hinting --desubroutinize --name-IDs='*' --name-languages='*' \
    --output-file="$OUT/$face-SemiBold.ttf"
done
sha256sum "$OUT"/*-SemiBold.ttf
