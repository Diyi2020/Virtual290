#!/bin/bash
# Virtual290 — M0 board spike launcher (macOS / Linux)
# Serves this folder on localhost so the microphone and math fonts work.
# Double-click this file. If macOS refuses, right-click → Open → Open.

cd "$(dirname "$0")" || exit 1
PORT=8731
URL="http://localhost:$PORT/m0-board-spike.html"

# find something that can serve a directory
if   command -v python3 >/dev/null 2>&1; then SERVE=(python3 -m http.server "$PORT")
elif command -v python  >/dev/null 2>&1; then SERVE=(python  -m http.server "$PORT")
elif command -v npx     >/dev/null 2>&1; then SERVE=(npx --yes serve -l "$PORT" .)
elif command -v ruby    >/dev/null 2>&1; then SERVE=(ruby -run -e httpd . -p "$PORT")
elif command -v php     >/dev/null 2>&1; then SERVE=(php -S "localhost:$PORT")
else
  echo
  echo "  No local web server found (needs python3, node, ruby or php)."
  echo "  You can still use the demo: just double-click m0-board-spike.html."
  echo "  Everything works except the microphone — use the text box instead."
  echo
  read -r -p "  Press Return to open it that way. " _
  command -v open >/dev/null 2>&1 && open "m0-board-spike.html" || xdg-open "m0-board-spike.html"
  exit 0
fi

echo
echo "  Virtual290 — board spike"
echo "  Serving at $URL"
echo "  Leave this window open. Press Ctrl-C (or just close it) when you're done."
echo

( sleep 1.2
  if   command -v open     >/dev/null 2>&1; then open "$URL"
  elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
  fi ) &

"${SERVE[@]}"
