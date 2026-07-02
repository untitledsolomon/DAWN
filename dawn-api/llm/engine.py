"""
LLM Engine — abstracts local llama.cpp and DeepSeek API behind one interface.
Switch via LLM_MODE env var: "deepseek" | "local"
"""
from typing import AsyncGenerator, Optional
from config import settings
import logging

logger = logging.getLogger(__name__)

DAWN_SYSTEM_PROMPT = """You are DAWN — the internal knowledge layer and AI assistant for Regent, \
a digital systems and strategy firm based in Kampala, Uganda.

You were built by Solomon John. You have deep familiarity with:
- Regent's products: CRM, PM, Axis ERP (Uganda payroll/tax compliance), Forge CMS, DAWN itself
- Solomon's trading systems: Sentinel RL bot (PPO, EURUSD 1H), nyao_scalper (MT5)
- EconSim: a C++ and SFML town economy simulator Solomon is building
- Mabruk Atelier: a luxury fashion brand
- The Regent tech stack: Next.js, TypeScript, Supabase, Tailwind, FastAPI, Docker, Coolify
- Jarvis: the autonomous AI agent running on OpenClaw framework on Paperclip VPS (AlphaVPS)
- East African SME context and Uganda business landscape

When answering:
- Be precise and direct. Solomon moves fast and prefers concise, actionable responses.
- If knowledge graph context is provided below, treat it as your primary source of truth.
- Reference specific nodes when you draw from them.
- If context is missing or incomplete, say so clearly and answer from general knowledge.
- For code: write it fully, don't truncate.
- For reasoning tasks: think step by step but don't narrate the thinking process."""


class DeepSeekEngine:
    def __init__(self):
        from openai import AsyncOpenAI
        self.client = AsyncOpenAI(
            api_key=settings.deepseek_api_key,
            base_url=settings.deepseek_base_url,
        )
        self.model = settings.deepseek_model
        logger.info(f"DeepSeek engine initialised — model: {self.model}")

    async def stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=True,
            max_tokens=2048,
            temperature=0.7,
        )
        async for chunk in response:
            delta = chunk.choices[0].delta
            if delta.content:
                yield delta.content

    async def complete(self, messages: list[dict]) -> str:
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=False,
            max_tokens=1024,
            temperature=0.3,
        )
        return response.choices[0].message.content or ""


class LocalEngine:
    def __init__(self):
        from llama_cpp import Llama
        logger.info(f"Loading local model from: {settings.local_model_path}")
        self.llm = Llama(
            model_path=settings.local_model_path,
            n_ctx=settings.local_model_n_ctx,
            n_threads=settings.local_model_n_threads,
            verbose=False,
            chat_format="chatml",
        )
        logger.info("Local model loaded successfully")

    async def stream(self, messages: list[dict]) -> AsyncGenerator[str, None]:
        # llama_cpp is sync — wrap in generator
        output = self.llm.create_chat_completion(
            messages=messages,
            stream=True,
            max_tokens=2048,
            temperature=0.7,
        )
        for chunk in output:
            delta = chunk["choices"][0]["delta"]
            if "content" in delta and delta["content"]:
                yield delta["content"]

    async def complete(self, messages: list[dict]) -> str:
        output = self.llm.create_chat_completion(
            messages=messages,
            stream=False,
            max_tokens=1024,
            temperature=0.3,
        )
        return output["choices"][0]["message"]["content"] or ""


# ── Singleton ─────────────────────────────────────────────────────────────────

_engine: Optional[DeepSeekEngine | LocalEngine] = None


def get_engine() -> DeepSeekEngine | LocalEngine:
    global _engine
    if _engine is None:
        if settings.llm_mode == "local":
            if not settings.local_model_path:
                raise RuntimeError(
                    "LLM_MODE=local but LOCAL_MODEL_PATH is not set. "
                    "Download a GGUF model and set the path, or switch to LLM_MODE=deepseek."
                )
            _engine = LocalEngine()
        else:
            if not settings.deepseek_api_key:
                raise RuntimeError("LLM_MODE=deepseek but DEEPSEEK_API_KEY is not set.")
            _engine = DeepSeekEngine()
    return _engine


def build_messages(
    user_message: str,
    context: str,
    history: list[dict],
) -> list[dict]:
    """Assemble the full message list for the LLM."""
    system = DAWN_SYSTEM_PROMPT
    if context:
        system += f"\n\n─── KNOWLEDGE GRAPH CONTEXT ───\n{context}\n────────────────────────────────"

    messages = [{"role": "system", "content": system}]

    # Include last 10 turns of history to stay within context
    for turn in history[-10:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": user_message})
    return messages
