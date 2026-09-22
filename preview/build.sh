#!/usr/bin/env bash
# Assembles standalone preview pages from src/frame.css + src/theme-*.css + src/body.html
set -euo pipefail
cd "$(dirname "$0")"

names=(a:chancery:"A — Chancery":"Classic executive serif"
       b:meridian:"B — Meridian":"Modern sans, open"
       c:foundry:"C — Foundry":"Dense technical"
       d:atlas:"D — Atlas":"Bold editorial"
       e:blueprint:"E — Blueprint":"Engineering drawing, all mono"
       f:manifesto:"F — Manifesto":"Brutalist swiss"
       g:ledger:"G — Ledger":"Classical, margin column"
       h:nocturne:"H — Nocturne":"Dark, high contrast")

nav=""
for entry in "${names[@]}"; do
  IFS=: read -r _ slug label _ <<<"$entry"
  nav+="<a href=\"$slug.html\" data-slug=\"$slug\">$label</a>"
done

for entry in "${names[@]}"; do
  IFS=: read -r key slug label tag <<<"$entry"
  out="$slug.html"
  {
    echo "<meta charset=\"utf-8\"><title>Style $label</title>"
    echo "<style>"
    cat src/frame.css
    cat "src/theme-$key.css"
    cat <<'SWITCH'
/* ---- preview switcher (not part of the Word style) ---- */
.styleswitch { position: sticky; top: 0; z-index: 10; display: flex; flex-wrap: wrap; align-items: center;
  gap: .4rem; padding: .6rem 1rem; margin: -32px -16px 24px; background: #2b2e33;
  font: 600 12px/1 "Segoe UI", system-ui, sans-serif; }
.styleswitch .sw-name { color: #9aa0a6; font-weight: 400; margin-right: auto; letter-spacing: .08em;
  text-transform: uppercase; }
.styleswitch a { color: #d8dade; text-decoration: none; padding: .45rem .7rem; border-radius: 3px;
  background: #3a3e45; }
.styleswitch a:hover { background: #4a4f57; }
.styleswitch a.current { background: #fff; color: #16181c; }
SWITCH
    echo "</style>"
    echo "<nav class=\"styleswitch\"><span class=\"sw-name\">$tag</span>$nav</nav>"
    cat src/body.html
    echo "<script>document.querySelector('.styleswitch a[data-slug=\"$slug\"]').classList.add('current');</script>"
  } > "$out"
  echo "built $out"
done
