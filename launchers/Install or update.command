#!/bin/zsh
# Double-click to set up the research agent and content check on this Mac, or to
# update them after a new copy of the program is downloaded. Safe to run again.

cd "$(dirname "$0")/.." || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:/Library/Frameworks/Python.framework/Versions/Current/bin:$PATH"

pause() { read -k1 "?Press any key to close."; echo; }

# 1. Python 3.11 or newer, preferring one that can show the suburb window (tkinter).
# Homebrew's Python leaves tkinter out; python.org's includes it.
ok_version() { "$1" -c 'import sys; sys.exit(sys.version_info < (3, 11))' 2>/dev/null; }
has_tk() { "$1" -c 'import tkinter' >/dev/null 2>&1; }
PYTHON=""
FALLBACK=""
for name in python3.13 python3.12 python3.11 python3; do
  for candidate in ${(f)"$(whence -ap "$name" 2>/dev/null)"}; do
    ok_version "$candidate" || continue
    [[ -z "$FALLBACK" ]] && FALLBACK="$candidate"
    if has_tk "$candidate"; then
      PYTHON="$candidate"
      break 2
    fi
  done
done
if [[ -z "$PYTHON" && -z "$FALLBACK" ]]; then
  echo "Python 3.11 or newer is needed. Install it from python.org (Downloads, macOS),"
  echo "then double-click this file again."
  pause; exit 1
fi
if [[ -z "$PYTHON" ]]; then
  PYTHON="$FALLBACK"
  echo "Note: this Python can't show windows, so the suburb window will be skipped and"
  echo "the usual suburbs used. Python from python.org includes what's needed."
fi
echo "Using $("$PYTHON" --version)."

# 2. The program, in its own folder (.venv) inside the project. If the existing folder
# can't show windows but this Python can, it's rebuilt; it only holds installed packages.
if [[ -x .venv/bin/python ]] && ! has_tk .venv/bin/python && has_tk "$PYTHON"; then
  echo "Rebuilding the program's Python folder so it can show the suburb window..."
  "$PYTHON" -m venv --clear .venv || { echo "Couldn't rebuild it."; pause; exit 1; }
fi
if [[ ! -x .venv/bin/python ]]; then
  echo "Creating the program's own Python folder..."
  "$PYTHON" -m venv .venv || { echo "Couldn't create it."; pause; exit 1; }
fi
echo "Installing or updating the program. This needs the internet and takes a minute..."
.venv/bin/python -m pip install --quiet --upgrade pip >/dev/null 2>&1
if ! .venv/bin/python -m pip install --quiet .; then
  echo "The install didn't finish. Check the internet connection and try again."
  pause; exit 1
fi
echo "Program installed."

# 3. Checks for the other pieces, with what to do if one is missing.
echo
MISSING=0
if command -v claude >/dev/null 2>&1; then
  echo "OK  Claude Code is installed."
else
  echo "--  Claude Code is not installed. See the handover guide, Setting up."; MISSING=1
fi
if [[ -f config/settings.private.toml ]]; then
  echo "OK  Your private settings file is in place."
else
  echo "--  config/settings.private.toml is missing. Copy it in from the file Kyle sent."; MISSING=1
fi
if [[ -f "$HOME/.zshrc" ]] && grep -q "BRAVE_API_KEY" "$HOME/.zshrc"; then
  echo "OK  A Brave key is saved (the key itself is not shown)."
else
  echo "--  No Brave key saved. The agent still runs, but won't search for missing websites."
fi
echo
if [[ $MISSING -eq 0 ]]; then
  echo "All set. Double-click 'Run research agent' to start."
else
  echo "Almost there: fix the items marked -- above, then run this again."
fi
pause
