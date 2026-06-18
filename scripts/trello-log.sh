#!/usr/bin/env bash
# Publish a work-log card to Trello (board + list from .env).
#
# Usage:
#   ./scripts/trello-log.sh "card title" "description text"
#   ./scripts/trello-log.sh "description text"          # auto-dated title
#   echo "long markdown body" | ./scripts/trello-log.sh "card title"
#   ./scripts/trello-log.sh -l <listId> "title" "body"  # override target list
#
# Credentials/IDs come from .env: TRELLO_API_KEY, TRELLO_TOKEN, TRELLO_BOARD_ID, TRELLO_LIST_ID
set -euo pipefail
cd "$(dirname "$0")/.."

[ -f .env ] || { echo "ERROR: .env not found" >&2; exit 1; }
# shellcheck disable=SC1090
eval "$(grep -E '^TRELLO_' .env | sed 's/^/export /')"
: "${TRELLO_API_KEY:?missing in .env}" "${TRELLO_TOKEN:?missing in .env}"

LIST_ID="${TRELLO_LIST_ID:-}"
if [ "${1:-}" = "-l" ]; then LIST_ID="$2"; shift 2; fi
[ -n "$LIST_ID" ] || { echo "ERROR: no list id (set TRELLO_LIST_ID or pass -l)" >&2; exit 1; }

TODAY="$(date +%F)"
if [ "$#" -ge 2 ]; then
  NAME="$1"; DESC="$2"
elif [ "$#" -eq 1 ]; then
  if [ -t 0 ]; then NAME="📋 工作日誌 $TODAY"; DESC="$1"
  else NAME="$1"; DESC="$(cat)"; fi
else
  NAME="📋 工作日誌 $TODAY"; DESC="$(cat)"
fi

curl -s -X POST "https://api.trello.com/1/cards" \
  --data-urlencode "key=$TRELLO_API_KEY" \
  --data-urlencode "token=$TRELLO_TOKEN" \
  --data-urlencode "idList=$LIST_ID" \
  --data-urlencode "name=$NAME" \
  --data-urlencode "desc=$DESC" \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print('✅ card created:', d.get('shortUrl') or d)"
