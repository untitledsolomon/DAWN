# DAWN v1.0
**Digital AI Working Network** — Knowledge layer for Regent

---

## Architecture
```
Supabase (graph DB)  ←→  FastAPI (dawn-api)  ←→  Next.js (dawn-ui)
                              ↕
                     DeepSeek API (now)
                     llama.cpp local (later)
```

---

## Step 1 — Supabase schema

Run `dawn_schema.sql` in your Supabase SQL editor.
Order matters: extensions first, then enums, then tables, then functions, then seed data.

---

## Step 2 — Backend (dawn-api)

### Local dev
```bash
cd dawn-api
cp .env.example .env       # Fill in SUPABASE_URL, SUPABASE_SERVICE_KEY, DEEPSEEK_API_KEY
pip install -r requirements.txt
uvicorn main:app --reload --port 8000 --loop asyncio
```

### VPS (new 8GB box, via Docker)
```bash
# On the new VPS
git clone your-repo /home/solomon/dawn
cd /home/solomon/dawn/dawn-api
cp .env.example .env       # Fill in production values
docker compose up -d
```

API docs available at: `http://your-vps:8000/docs`

### Switching to local model (when ready)
1. Download a GGUF model:
   ```bash
   # Recommended: Qwen2.5-3B-Instruct-Q4_K_M.gguf (~2GB)
   wget https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF/resolve/main/qwen2.5-3b-instruct-q4_k_m.gguf \
     -O /home/solomon/models/qwen2.5-3b-q4.gguf
   ```
2. Update `.env`:
   ```
   LLM_MODE=local
   LOCAL_MODEL_PATH=/models/qwen2.5-3b-q4.gguf
   LOCAL_MODEL_N_THREADS=4
   ```
3. Restart the container.

---

## Step 3 — Frontend (dawn-ui)

### Local dev
```bash
cd dawn-ui
cp .env.local.example .env.local   # Fill in API URL and key
npm install
npm run dev
# Opens at http://localhost:3000
```

### Deploy to Vercel
```bash
cd dawn-ui
vercel deploy --prod
# Set env vars in Vercel dashboard:
#   NEXT_PUBLIC_DAWN_API_URL = https://dawn-api.regentplatform.com
#   NEXT_PUBLIC_DAWN_API_KEY = your-api-key
```

---

## Step 4 — Seed your first nodes

Once the API is running, open the Knowledge page and create a few root nodes manually:
- **Regent** (entity) — tagged: regent
- **Jarvis** (entity) — tagged: jarvis, ai
- **Paperclip VPS** (entity) — tagged: infrastructure
- **Sentinel** (entity) — tagged: trading
- **EconSim** (entity) — tagged: econ-sim

Then use the Ingest page to pull in your repos.

---

## Connecting Jarvis to DAWN

Add this to Jarvis's tool definitions:
```python
async def query_dawn(question: str) -> str:
    """Query DAWN knowledge graph for Regent-specific context."""
    import httpx
    async with httpx.AsyncClient() as client:
        # Use the non-streaming complete endpoint
        res = await client.post(
            "https://dawn-api.regentplatform.com/search/",
            headers={"X-API-Key": DAWN_API_KEY},
            params={"q": question, "limit": 5},
        )
        nodes = res.json()
        if not nodes:
            return "No relevant context found in DAWN."
        return "\n".join(f"[{n['title']}]: {n['body']}" for n in nodes if n.get('body'))
```

---

## File structure
```
dawn/
├── README.md
├── dawn_schema.sql          # Run this in Supabase first
├── dawn-api/                # FastAPI backend
│   ├── main.py
│   ├── config.py
│   ├── requirements.txt
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── .env.example
│   ├── db/client.py         # All Supabase queries
│   ├── llm/
│   │   ├── engine.py        # DeepSeek / local model abstraction
│   │   └── tools.py         # Graph retrieval pipeline
│   ├── routers/
│   │   ├── chat.py          # POST /chat/ — streaming SSE
│   │   ├── nodes.py         # CRUD /nodes/
│   │   ├── search.py        # GET /search/
│   │   └── ingest.py        # POST /ingest/repo, /ingest/document
│   └── ingestion/
│       ├── repo.py          # Git repo ingester
│       └── memory.py        # Conversation memory extractor
└── dawn-ui/                 # Next.js frontend
    ├── package.json
    ├── tailwind.config.ts
    ├── src/app/
    │   ├── chat/page.tsx    # Main chat interface
    │   ├── nodes/page.tsx   # Knowledge base browser
    │   └── memory/page.tsx  # Memory review + ingestion
    ├── src/components/
    │   ├── layout/Sidebar.tsx
    │   ├── chat/ChatWindow.tsx
    │   ├── chat/Message.tsx
    │   ├── chat/ToolCallIndicator.tsx
    │   ├── nodes/NodeCard.tsx
    │   └── nodes/NodeForm.tsx
    └── src/lib/
        ├── api.ts           # All API calls
        └── types.ts         # Shared TypeScript types
```
