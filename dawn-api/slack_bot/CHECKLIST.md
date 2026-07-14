# Slack Setup Checklist

## Phase 1: Slack Integration (Done — code is ready)

### What I Built
- [x] `slack_bot/app.py` — Lazy-init Bolt app with DM, mention, and slash command handlers
- [x] `slack_bot/manifest.yaml` — One-click Slack app config (with files:read scope)
- [x] `slack_bot/README.md` — Full setup docs
- [x] `routers/slack.py` — API endpoints to start/stop/status/send/upload
- [x] `main.py` — Updated with Slack router + auto-start on boot
- [x] `requirements.txt` — Added slack-bolt, slack-sdk

### Key Architecture Change (v2)
- [x] Bot now calls **`/agent/` endpoint** instead of `/chat/`
- [x] Full DAWN agent with tools available from Slack
- [x] File attachment support (download from Slack → ingest into DAWN)
- [x] New commands: `/regent`, `/analyze`
- [x] Long message splitting (handles responses >40K chars)
- [x] `files:read` OAuth scope added to manifest

### What YOU Need to Do (5 minutes)

- [ ] **Go to** https://api.slack.com/apps
- [ ] **Click** "Create New App" → "From Manifest"
- [ ] **Paste** the contents of `slack_bot/manifest.yaml`
- [ ] **Enable** Socket Mode (Settings → Socket Mode → On)
- [ ] **Install** to Workspace (Settings → OAuth & Permissions → Install to Workspace)
- [ ] **Copy** the Bot Token (starts with `xoxb-`)
- [ ] **Create** an App-Level Token (Settings → Basic Information → App-Level Tokens → Generate Token)
      - Name: `dawn-socket`
      - Scope: `connections:write`
- [ ] **Copy** the App Token (starts with `xapp-`)
- [ ] **Copy** the Signing Secret (Settings → Basic Information → Signing Secret)
- [ ] **Add to .env:**
  ```
  SLACK_BOT_TOKEN=xoxb-...
  SLACK_APP_TOKEN=xapp-...
  SLACK_SIGNING_SECRET=...
  ```
- [ ] **Restart** DAWN API
- [ ] **Test:** DM @DAWN in Slack → "Hello, what can I help you with?"

## Phase 2: Axis ERP Monetization (Next)

- [ ] Package Axis as multi-tenant SaaS
- [ ] Add URA e-filing integration
- [ ] Add NSSF auto-calculation
- [ ] Add MTN MoMo payment collection (DGateway)
- [ ] Create Slack `/payroll` command
- [ ] Onboard 3-5 pilot customers

## Phase 3: CRM + DAWN SaaS

- [ ] Package CRM as multi-tenant SaaS
- [ ] Sell DAWN as a Slack bot to other businesses
- [ ] Create referral program

## Phase 4: Full Autonomy

- [ ] Jarvis integration for auto-deployments
- [ ] Automated billing and reconciliation
- [ ] Client onboarding automation
- [ ] Weekly business reports to Slack
