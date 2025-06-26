#!/usr/bin/env bash
# start.sh – control projesini yeni bir terminal penceresinde çalıştır

CMD="cd /home/tatek/Documents/control && source venv/bin/activate && python3 main.py"

open_term () {
  # $1 = terminal binary, $2 = arg dizisi
  if command -v "$1" >/dev/null 2>&1; then
    "$1" ${2} "$CMD; exec bash"
    exit 0
  fi
}

# 1) GNOME Terminal
open_term gnome-terminal "-- bash -c"

# 2) Xfce4-terminal
open_term xfce4-terminal "--hold -e bash -c"

# 3) Konsole (KDE)
open_term konsole "-e bash -c"

# 4) xterm (evrensel yedek)
open_term xterm "-hold -e bash -c"

echo "Uygun terminal emülatörü bulunamadı. Lütfen GNOME Terminal, Xfce4-terminal, Konsole veya xterm kurun." >&2
exit 1
