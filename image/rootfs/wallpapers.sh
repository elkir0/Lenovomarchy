#!/usr/bin/env bash
# Downscale stock Omarchy 4K/5K theme backgrounds so none exceeds 2000 px on
# its longest side (matching the 1200x2000 panel of the Lenovo Yoga Tab 11).

set -euo pipefail

MAX_EDGE=2000
JPG_QUALITY=88
BG_GLOB="/usr/share/omarchy/themes/*/backgrounds/*"

command -v magick >/dev/null 2>&1 || { echo "ERROR: ImageMagick (magick) not installed" >&2; exit 1; }

shopt -s nullglob
files=( $BG_GLOB )
shopt -u nullglob

if [[ ${#files[@]} -eq 0 ]]; then
    echo "ERROR: no theme backgrounds matched $BG_GLOB" >&2
    exit 1
fi

resized=0
kept=0
bytes_before=0
bytes_after=0

for f in "${files[@]}"; do
    [[ -f "$f" && ! -L "$f" ]] || continue

    sz_before=$(stat -c '%s' "$f")
    bytes_before=$((bytes_before + sz_before))

    read -r w h < <(magick identify -format '%w %h\n' "$f[0]")
    long=$(( w > h ? w : h ))

    if (( long <= MAX_EDGE )); then
        bytes_after=$((bytes_after + sz_before))
        kept=$((kept + 1))
        continue
    fi

    ext="${f##*.}"
    tmp="${f}.lenovomarchy-tmp.${ext}"
    case "${ext,,}" in
        jpg|jpeg)
            magick "$f" -auto-orient -resize "${MAX_EDGE}x${MAX_EDGE}>" -strip \
                -sampling-factor 4:2:0 -interlace Plane -quality "$JPG_QUALITY" "$tmp"
            ;;
        png)
            magick "$f" -auto-orient -resize "${MAX_EDGE}x${MAX_EDGE}>" -strip \
                -define png:compression-level=9 "$tmp"
            ;;
        *)
            rm -f "$tmp"
            bytes_after=$((bytes_after + sz_before))
            kept=$((kept + 1))
            continue
            ;;
    esac

    chmod 0644 "$tmp"
    mv -f "$tmp" "$f"
    sz_after=$(stat -c '%s' "$f")
    bytes_after=$((bytes_after + sz_after))
    resized=$((resized + 1))
done

printf '==> Wallpapers: %d resized (>%d px), %d kept; %.1f MiB -> %.1f MiB\n' \
    "$resized" "$MAX_EDGE" "$kept" \
    "$(awk "BEGIN {print $bytes_before/1048576}")" \
    "$(awk "BEGIN {print $bytes_after/1048576}")"
