#!/bin/zsh
# Double-click, choose a Word file of drafted content, and get a list of things to check.
# The check runs on this Mac only and sends nothing anywhere.

cd "$(dirname "$0")/.." || exit 1

if [[ -x ".venv/bin/content-check" ]]; then
  CHECK=".venv/bin/content-check"
elif [[ -x "$HOME/.venvs/org-research-agent/bin/content-check" ]]; then
  CHECK="$HOME/.venvs/org-research-agent/bin/content-check"
else
  echo "The content check isn't installed yet. See the handover guide, section on installing."
  read -k1 "?Press any key to close."
  exit 1
fi

FILE=$(osascript -e 'POSIX path of (choose file with prompt "Choose the Word file to check" of type {"org.openxmlformats.wordprocessingml.document"})' 2>/dev/null)
if [[ -z "$FILE" ]]; then
  echo "No file chosen."
  exit 0
fi

# The business's own number and approved disclaimer, if saved, so the check allows them.
OPTIONS=()
[[ -f config/business-phone.private.txt ]] && OPTIONS+=(--business-phone "$(<config/business-phone.private.txt)")
[[ -f config/disclaimer.private.txt ]] && OPTIONS+=(--disclaimer-file config/disclaimer.private.txt)

REPORT="${FILE%.docx} - check results.txt"
"$CHECK" "${OPTIONS[@]}" "$FILE" > "$REPORT" 2>&1
echo "Results saved next to your Word file:"
echo "$REPORT"
open -e "$REPORT"
