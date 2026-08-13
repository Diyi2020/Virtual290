#!/bin/bash
# Virtual290 — launcher (macOS / Linux).
# Serves this folder on localhost so the microphone and math fonts work.
#
# Double-click me. If macOS complains:
#   "unidentified developer"  -> right-click me -> Open -> Open   (once only)
#   "you do not have permission" / nothing happens ->
#        open Terminal and run:   bash start-mac.command
#
# NOTE: we probe tools by RUNNING them, not by checking they exist. A stock Mac
# ships a /usr/bin/python3 stub that pops the Xcode-tools install dialog instead
# of running Python — "command -v python3" finds it and lies. System ruby has no
# such trap, so it is tried first.

cd "$(dirname "$0")" || exit 1

# find a free port (connection refused = free)
PORT=""
for P in 8731 8732 8733 8734; do
  if ! (echo > "/dev/tcp/127.0.0.1/$P") 2>/dev/null; then PORT=$P; break; fi
done
[ -z "$PORT" ] && PORT=8735
URL="http://localhost:$PORT/m1-slice-lecture.html"

open_url() {
  ( sleep 1.2
    if   command -v open     >/dev/null 2>&1; then open "$URL"
    elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$URL"
    fi ) &
}

banner() {
  echo
  echo "  Virtual290"
  echo "  Serving at $URL   (server: $1)"
  echo "  Leave this window open. Press Ctrl-C, or just close it, when done."
  echo
}

# ---- probes actually RUN each tool ----------------------------------------
if ruby -e 'exit 0' >/dev/null 2>&1; then
  banner ruby; open_url
  exec ruby -run -e httpd . -p "$PORT"
fi

if python3 -c 'pass' >/dev/null 2>&1; then
  banner python3; open_url
  exec python3 -m http.server "$PORT"
fi

if python -c 'pass' >/dev/null 2>&1; then
  banner python; open_url
  exec python -m http.server "$PORT"
fi

if npx --version >/dev/null 2>&1; then
  banner "npx serve"; open_url
  exec npx --yes serve -l "$PORT" .
fi

echo
echo "  No usable web server found (tried ruby, python3, python, npx)."
echo "  Opening the demo directly instead — everything works except the"
echo "  microphone in Chrome/Edge; type your questions in the text box."
echo
command -v open >/dev/null 2>&1 && open "m1-slice-lecture.html" || xdg-open "m1-slice-lecture.html"
read -r -p "  Press Return to close this window. " _
