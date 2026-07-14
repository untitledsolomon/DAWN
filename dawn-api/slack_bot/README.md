# DAWN Slack Bot

DAWN's interface to Slack. Lets you manage Regent entirely from Slack.

## Architecture

```
Slack (Socket Mode) → Slack Bolt App → DAWN Agent API (HTTP) → Full DAWN agent with tools
```

**Key change from v1:** The bot now calls DAWN's `/agent/` endpoint instead of `/chat/`.
This means you get the **full DAWN agent** in Slack — with tool access (knowledge graph,
filesystem, git, web search, OMNI, OSINT, pentest, decision workflows, ontology, charts,
explainers) — not a dumbed-down chat proxy.

The Bolt app runs in a background thread inside the DAWN API process.
It uses **Socket Mode** — no public HTTP endpoint needed, no ngrok, no port forwarding.

## What You Can Do Now

### Talk to DAWN (full agent mode)
- **DM @DAWN** — anything you'd ask me here, you can ask from Slack
- **@DAWN in a channel** — mention DAWN with your question
- **`/dawn <question>`** — slash command in any channel

### Share files
- **Attach files in DMs** — PDFs, spreadsheets, images, code, documents
- DAWN ingests them into the knowledge graph and can answer questions about them
- **`/analyze <question>`** — analyze a file or situation

### Manage Regent
- **`/regent <question>`** — ask about Regent products, clients, team, projects
- **`/status`** — system health check
- **`/revenue`** — revenue summary
- **`/leads`**, **`/pipeline`**, **`/team`**, **`/projects`**, **`/dashboard`** — CRM commands

### What DAWN can do for you
- Search the knowledge graph for anything about Regent
- Read and write files in the DAWN sandbox
- Clone and inspect git repositories
- Search the web for current information
- Run OSINT reconnaissance (whois, DNS, Shodan, certificate search)
- Run security testing (port scanning, web scanning, etc.)
- Query OMNI geospatial data (aircraft, satellites, ships, earthquakes, weather)
- Execute decision workflows
- Create charts and visualizations
- Generate explainer animations

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
- Use `/regent <question>` for Regent-specific queries
- Share a file and ask DAWN about it

## Commands

| Command | Description |
|---------|-------------|
| `@DAWN <message>` | Mention DAWN in a channel (full agent mode) |
| DM `@DAWN` | Direct message DAWN (full agent mode, supports file attachments) |
| `/dawn <question>` | Ask DAWN anything — full agent mode with tools |
| `/regent <question>` | Ask about Regent — products, clients, team, projects |
| `/analyze <question>` | Analyze a file, situation, or data |
| `/status` | System health check |
| `/revenue` | Revenue summary |
| `/leads [filter]` | CRM lead management |
| `/pipeline` | Pipeline funnel summary |
| `/team [add ...]` | Team roster management |
| `/projects [all\|add ...]` | Project management |
| `/dashboard` | Full team dashboard overview |

## File Support

DAWN can ingest and analyze these file types when you share them in Slack:

- **PDF** — text extraction + OCR for scanned documents
- **Word** (.docx) — full text extraction
- **Excel** (.xlsx, .xls) — spreadsheet data extraction
- **CSV** — tabular data
- **PowerPoint** (.pptx) — slide content
- **Images** — OCR via Tesseract
- **Code** (.py, .js, .ts, .html, .css, .json, .yaml, etc.)
- **Markdown** (.md)
- **EPUB** — ebook format
- **Text** (.txt, .log, .rtf)
- **SVG** — vector graphics

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
| POST | `/slack/upload` | Upload a file to DAWN's knowledge graph |
| GET | `/slack/setup` | Setup instructions |
| GET | `/slack/sessions` | List Slack → DAWN session mappings |

## Development

```bash
# Install dependencies
pip install slack-bolt slack-sdk

# Run standalone (for testing)
python -m slack_bot.app

# Run with API
uvicorn main:app --reload
```
