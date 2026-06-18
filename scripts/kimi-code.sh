#!/usr/bin/env bash
# Launch Claude Code's agent UI powered by Kimi Code (kimi-for-coding) instead of
# your Anthropic subscription. All implementation tokens are billed to Kimi.
#
# Usage:
#   ./scripts/kimi-code.sh                 # interactive session
#   ./scripts/kimi-code.sh -p "implement task 1 from task master, then mark it done"
#
# The Kimi key is read from .env (OPENAI_COMPATIBLE_API_KEY) so it is never hard-coded here.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f .env ]; then echo "ERROR: .env not found in repo root" >&2; exit 1; fi
KEY="$(grep -E '^OPENAI_COMPATIBLE_API_KEY' .env | head -1 | cut -d'"' -f2)"
if [ -z "${KEY:-}" ]; then echo "ERROR: OPENAI_COMPATIBLE_API_KEY missing in .env" >&2; exit 1; fi

# Point Claude Code at Kimi's Anthropic-compatible endpoint.
# Claude Code appends /v1/messages to ANTHROPIC_BASE_URL.
export ANTHROPIC_BASE_URL="https://api.kimi.com/coding"
export ANTHROPIC_AUTH_TOKEN="$KEY"
export ANTHROPIC_MODEL="kimi-for-coding"
export ANTHROPIC_SMALL_FAST_MODEL="kimi-for-coding"
# Kimi requires temperature=1; Claude Code already uses 1 by default.
# Unset any subscription key so this session uses the Kimi token, not your plan.
unset ANTHROPIC_API_KEY 2>/dev/null || true

echo "▶ Claude Code → Kimi (kimi-for-coding). Billed to Kimi, not your Claude plan."
exec claude "$@"
