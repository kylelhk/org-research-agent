#!/bin/zsh
# Double-click to research local organisations and open the results in Excel.
# Runs on this Mac only. Close this window to stop at any time.

cd "$(dirname "$0")/.." || exit 1
export PATH="$HOME/.local/bin:/opt/homebrew/bin:/usr/local/bin:$PATH"

# The Brave key lives in ~/.zshrc, which a double-clicked file doesn't load by itself.
if [[ -z "$BRAVE_API_KEY" && -f "$HOME/.zshrc" ]]; then
  source "$HOME/.zshrc" >/dev/null 2>&1
fi

# Use the project's own Python environment.
if [[ -x ".venv/bin/org-research" ]]; then
  RUN=".venv/bin/org-research"
elif [[ -x "$HOME/.venvs/org-research-agent/bin/org-research" ]]; then
  RUN="$HOME/.venvs/org-research-agent/bin/org-research"
else
  echo "The research agent isn't installed yet. See the handover guide, section on installing."
  read -k1 "?Press any key to close."
  exit 1
fi

if ! command -v claude >/dev/null 2>&1; then
  echo "Claude Code isn't installed or isn't on this Mac's path. See the handover guide."
  read -k1 "?Press any key to close."
  exit 1
fi

# Ask whether to look up missing websites with Brave (only offered when a key is saved).
EXTRA=()
if [[ -n "$BRAVE_API_KEY" ]]; then
  ANSWER=$(osascript -e 'button returned of (display dialog "Search for missing websites with Brave first?" & return & return & "This finds more practices to research. It sends only each practice'"'"'s name and suburb to Brave." buttons {"No", "Yes"} default button "Yes" with title "Research agent")' 2>/dev/null)
  [[ "$ANSWER" == "Yes" ]] && EXTRA=(--find-websites)
else
  echo "No Brave key saved, so missing websites won't be searched for."
fi

echo "Researching. Leave this window open until the Excel list opens."
echo
"$RUN" "${EXTRA[@]}"
STATUS=$?

LATEST=$(ls -t output/research-*.xlsx 2>/dev/null | head -1)
echo
if [[ $STATUS -eq 0 && -n "$LATEST" ]]; then
  echo "Done. Opening $LATEST"
  open "$LATEST"
else
  echo "The run didn't finish. Check the messages above, and see Troubleshooting in the handover guide."
fi
read -k1 "?Press any key to close."
