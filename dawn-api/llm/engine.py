"""
LLM Engine — abstracts local llama.cpp and DeepSeek API behind one interface.
Switch via LLM_MODE env var: "deepseek" | "local"
"""
from typing import AsyncGenerator, Optional
from dataclasses import dataclass, field

from pymupdf import message
from config import settings
import logging
import json

logger = logging.getLogger(__name__)


@dataclass
class ToolCallRequest:
    """One tool call the model wants to make, normalised across backends."""
    id: str
    name: str
    args: dict


@dataclass
class CompletionResult:
    """Result of complete_with_tools() — either a final text answer, or tool_calls to execute."""
    content: str = ""
    tool_calls: list[ToolCallRequest] = field(default_factory=list)

    @property
    def wants_tool_call(self) -> bool:
        return len(self.tool_calls) > 0

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

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
        max_tokens: int = 8192,
    ) -> CompletionResult:
        """
        Like complete(), but offers the model a set of callable tools
        (OpenAI/DeepSeek function-calling spec, e.g. registry.specs()).
        Returns either final text content, or a list of tool calls to run.
        """
        response = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            stream=False,
            max_tokens=max_tokens,
            temperature=0.1,  # low on purpose — determinism matters more than
                              # creativity when deciding whether to call a tool
        )
        choice = response.choices[0]
        message = choice.message

        if message.tool_calls:
            calls = []
            for tc in message.tool_calls:
                args = {}
                if tc.function.arguments:
                    try:
                        args = json.loads(tc.function.arguments)
                    except json.JSONDecodeError as e:
                        if choice.finish_reason == "length":
                            err = (
                                "Tool call arguments were truncated because the response "
                                "hit the max_tokens limit before finishing. Break large "
                                "file writes into smaller chunks, or write the file in "
                                "multiple sequential 'write'/'append' calls."
                            )
                        else:
                            err = f"Tool call arguments were not valid JSON: {e}"
                        logger.warning(f"{err} Raw (truncated): {tc.function.arguments[:200]}...")
                        args = {"__parse_error__": err}
                calls.append(ToolCallRequest(id=tc.id, name=tc.function.name, args=args))
            return CompletionResult(content=message.content or "", tool_calls=calls)

        return CompletionResult(content=message.content or "")

    def tool_result_message(self, tool_call_id: str, tool_name: str, result_json: str) -> dict:
        """Build the 'tool' role message DeepSeek expects after a tool call."""
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "name": tool_name,
            "content": result_json,
        }

    def assistant_tool_call_message(self, content: str, tool_calls: list[ToolCallRequest]) -> dict:
        """Build the assistant message that recorded the tool call(s), for history."""
        return {
            "role": "assistant",
            "content": content or None,
            "tool_calls": [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {"name": tc.name, "arguments": json.dumps(tc.args)},
                }
                for tc in tool_calls
            ],
        }


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

    async def complete_with_tools(
        self,
        messages: list[dict],
        tools: list[dict],
    ) -> CompletionResult:
        """
        Tool-calling support depends entirely on the loaded GGUF's chat
        template (e.g. models fine-tuned on ChatML-with-functions or
        Hermes-style function calling). Rather than silently returning
        plain text and pretending tools were considered, this raises so
        the caller can fall back or surface a clear error — flip this on
        deliberately once you've confirmed your local model actually
        supports function calling in llama-cpp-python's format.
        """
        raise NotImplementedError(
            "LocalEngine.complete_with_tools() is not implemented — tool-calling "
            "support varies by GGUF chat template and hasn't been verified for "
            "the currently configured local model. Use LLM_MODE=deepseek for "
            "agent/tool workflows until this is validated."
        )


# ── Singleton ────────────────────────────────────────────────────────────────

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
        system += f"\n\n─── KNOWLEDGE GRAPH CONTEXT ───\n{context}\n─────────────────────────────"

    messages = [{"role": "system", "content": system}]

    # Include last 10 turns of history to stay within context
    for turn in history[-10:]:
        messages.append({"role": turn["role"], "content": turn["content"]})

    messages.append({"role": "user", "content": user_message})
    return messages