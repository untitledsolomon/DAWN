#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# Slack Bot Setup Script for DAWN
# ──────────────────────────────────────────────────────────────────────────────
# This script installs dependencies and validates the Slack bot configuration.
# Run it after setting up your Slack app at api.slack.com.
#
# Usage:
#   chmod +x scripts/setup_slack.sh
#   ./scripts/setup_slack.sh
#
# Prerequisites:
#   1. Go to https://api.slack.com/apps
#   2. Click "Create New App" → "From Manifest"
#   3. Paste the contents of slack_bot/manifest.yaml
#   4. After creation, enable Socket Mode
#   5. Install to Workspace (get Bot Token)
#   6. Create App-Level Token with "connections:write" scope
#   7. Copy Signing Secret from Basic Information
# ──────────────────────────────────────────────────────────────────────────────

set -e

echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║           DAWN Slack Bot Setup                               ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

# ── Check Python ──────────────────────────────────────────────────────────
echo "📋 Checking Python..."
python3 --version || { echo "❌ Python 3 required"; exit 1; }

# ── Install dependencies ──────────────────────────────────────────────────
echo ""
echo "📦 Installing Slack dependencies..."
pip install slack-bolt slack-sdk 2>&1 | tail -3
echo "✅ Slack SDK installed"

# ── Check for .env ────────────────────────────────────────────────────────
echo ""
echo "📋 Checking environment configuration..."
if [ ! -f .env ]; then
    echo "⚠️  No .env file found. Creating from .env.example..."
    cp .env.example .env
    echo "   Edit .env and add your Slack tokens!"
else
    echo "✅ .env file exists"
fi

# ── Validate tokens ───────────────────────────────────────────────────────
echo ""
echo "🔑 Checking Slack tokens..."
BOT_TOKEN="${SLACK_BOT_TOKEN:-$(grep SLACK_BOT_TOKEN .env 2>/dev/null | cut -d= -f2)}"
APP_TOKEN="${SLACK_APP_TOKEN:-$(grep SLACK_APP_TOKEN .env 2>/dev/null | cut -d= -f2)}"
SIGNING_SECRET="${SLACK_SIGNING_SECRET:-$(grep SLACK_SIGNING_SECRET .env 2>/dev/null | cut -d= -f2)}"

if [ -z "$BOT_TOKEN" ] || [ "$BOT_TOKEN" = "xoxb-your-bot-token" ]; then
    echo "❌ SLACK_BOT_TOKEN not set or still placeholder"
    echo "   Get it from: https://api.slack.com/apps → Your App → OAuth & Permissions"
    echo "   Then add to .env: SLACK_BOT_TOKEN=xoxb-..."
else
    echo "✅ SLACK_BOT_TOKEN: ${BOT_TOKEN:0:15}..."
fi

if [ -z "$APP_TOKEN" ] || [ "$APP_TOKEN" = "xapp-your-app-token" ]; then
    echo "❌ SLACK_APP_TOKEN not set or still placeholder"
    echo "   Get it from: https://api.slack.com/apps → Your App → App-Level Tokens"
    echo "   Then add to .env: SLACK_APP_TOKEN=xapp-..."
else
    echo "✅ SLACK_APP_TOKEN: ${APP_TOKEN:0:15}..."
fi

if [ -z "$SIGNING_SECRET" ] || [ "$SIGNING_SECRET" = "your-signing-secret" ]; then
    echo "❌ SLACK_SIGNING_SECRET not set or still placeholder"
    echo "   Get it from: https://api.slack.com/apps → Your App → Basic Information"
    echo "   Then add to .env: SLACK_SIGNING_SECRET=..."
else
    echo "✅ SLACK_SIGNING_SECRET: ${SIGNING_SECRET:0:10}..."
fi

# ── Test import ───────────────────────────────────────────────────────────
echo ""
echo "🧪 Testing Slack import..."
python3 -c "
from slack_bolt import App
from slack_sdk import WebClient
print('   ✅ slack-bolt and slack-sdk imported successfully')
print(f'   slack-bolt: {__import__(\"slack_bolt\").__version__}')
" 2>&1

# ── Summary ───────────────────────────────────────────────────────────────
echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║  Setup Complete                                              ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""
echo "Next steps:"
echo "  1. Set your Slack tokens in .env (if not done)"
echo "  2. Restart DAWN API: docker-compose restart dawn-api"
echo "     OR if running directly: uvicorn main:app --reload"
echo "  3. Verify: curl http://localhost:8000/slack/status"
echo "  4. In Slack, DM @DAWN or use /dawn command"
echo ""
echo "📖 Full docs: slack_bot/manifest.yaml"
echo ""
