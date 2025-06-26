#!/usr/bin/env bash
# start_all.sh – main.py + camera_stream.py’yi ayrı pencerelerde başlat

PROJECT_DIR="/home/tatek/Documents/control"
CMD_BASE="cd $PROJECT_DIR && source venv/bin/activate"

# Hangi terminal emülatörü varsa yakala
find_term() {
  for t in gnome-terminal xfce4-terminal konsole xterm; do
    if command -v "$t" >/dev/null 2>&1; then echo "$t"; return 0; fi
  done
  return 1
}

TERM_BIN=$(find_term) || { echo "Uygun terminal bulunamadı." >&2; exit 1; }

# Seçilen terminale göre komut/durum bayrakları
case "$TERM_BIN" in
  gnome-terminal)  NEW="-- bash -c"           ;;
  xfce4-terminal)  NEW="--hold -e bash -c"    ;;
  konsole)         NEW="-e bash -c"           ;;
  xterm)           NEW="-hold -e bash -c"     ;;
esac

# İlk pencere: main.py
"$TERM_BIN" $NEW "$CMD_BASE && python3 main.py; exec bash" &

# İkinci pencere: camera_stream.py
"$TERM_BIN" $NEW "$CMD_BASE && python3 camera_stream.py; exec bash" &

exit 0
