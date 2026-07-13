#!/usr/bin/env python3
"""
Standalone Slack bot runner.
Use this to run the Slack bot independently of the DAWN API for testing.

Usage:
    python scripts/run_slack_bot.py

Requires these env vars:
    SLACK_BOT_TOKEN=xoxb-...
    SLACK_APP_TOKEN=xapp-...
    SLACK_SIGNING_SECRET=...
    DAWN_API_URL=http://localhost:8000 (optional, default)
    DAWN_API_KEY=dev-key (optional, default)
"""
import os
import sys
import logging

# Add parent dir to path so we can import slack_bot
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

# Validate tokens
required = ["SLACK_BOT_TOKEN", "SLACK_APP_TOKEN", "SLACK_SIGNING_SECRET"]
missing = [v for v in required if not os.environ.get(v)]
if missing:
    print(f"❌ Missing required env vars: {', '.join(missing)}")
    print("   Set them and try again.")
    sys.exit(1)

from slack_bot.app import start_slack_bot
print("🚀 Starting DAWN Slack Bot...")
start_slack_bot()
