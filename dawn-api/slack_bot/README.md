# DAWN Slack Bot

DAWN's interface to Slack. Lets you manage Regent entirely from Slack.

## Architecture

```
Slack (Socket Mode) → Slack Bolt App → DAWN API (HTTP) → LLM + DB
```

The Bolt app runs in a background thread inside the DAWN API process.
It uses **Socket Mode** — no public HTTP endpoint needed, no ngrok, no port forwarding.

## Setup (5 minutes)

### 1. Create the Slack App

Go to https://api.slack.com/apps → **Create New App** → **From Manifest**

Copy the entire contents of `slack_bot/manifest.yaml` and paste it in.

### 2. Configure the App

After creation:

1. **Socket Mode** → Enable it
2. **OAuth & Permissions** → **Install to Workspace** → Copy the **Bot Token** (starts with `xoxb-`)
3. **Basic Information** → **App-Level Tokens** → **Generate Token**
   - Name: `dawn-socket`
   - Scope: `connections:write`
   - Copy the token (starts with `xapp-`)
4. **Basic Information** → Copy the **Signing Secret**

### 3. Set Environment Variables

Add to your `.env` file:

```bash
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_APP_TOKEN=xapp-your-app-token
SLACK_SIGNING_SECRET=your-signing-secret
```

### 4. Restart DAWN

```bash
# If using Docker:
docker-compose restart dawn-api

# If running directly:
uvicorn main:app --reload
```

The Slack bot starts automatically on API startup if tokens are configured.

### 5. Verify

```bash
curl http://localhost:8000/slack/status
# → {"running":true,"configured":true,"bot_token_set":true,"app_token_set":true}
```

Then in Slack:
- DM **@DAWN** anything
- Use `/dawn <question>` in any channel
- Use `/status` for system health
- Use `/revenue` for revenue summary

## Commands

| Command | Description |
|---------|-------------|
| `@DAWN <message>` | Mention DAWN in a channel |
| DM `@DAWN` | Direct message DAWN |
| `/dawn <question>` | Ask DAWN anything |
| `/status` | System health check |
| `/revenue` | Revenue summary |
| `/payroll <company>` | Run payroll (Phase 2) |
| `/invoice <client> <amount>` | Generate invoice (Phase 2) |

## Channel Monitoring

DAWN passively monitors these channels for actionable content:

- **#sales** — New leads, deal updates
- **#support** — Client issues, questions
- **#ops** — System health, deployments
- **#billing** — Payment issues, invoices
- **#general** — General business chat

## API Endpoints

| Method | Path | Description |
|--------|------|-------------|
| POST | `/slack/start` | Start the Slack bot |
| POST | `/slack/stop` | Stop the Slack bot |
| GET | `/slack/status` | Check if bot is running |
| POST | `/slack/send` | Send a message to a channel |
| GET | `/slack/setup` | Setup instructions |

## Development

```bash
# Install dependencies
pip install slack-bolt slack-sdk

# Run standalone (for testing)
python -m slack_bot.app

# Run with API
uvicorn main:app --reload
```
