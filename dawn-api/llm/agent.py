"""
Agent loop. Ties together: engine.complete_with_tools() + tools.registry +
tools.executor, iterating until the model returns a final answer (no more
tool calls) or max_iterations is hit.

Deliberately mirrors the event vocabulary already established in
routers/chat.py (thinking / tool / token / done) so the frontend can extend
its existing SSE handler rather than build a second one. New event types
added here: tool_call, tool_result, iteration_limit, warning.

This module yields dicts, not raw SSE strings — routers/agent.py is
responsible for formatting them with the existing sse() helper, keeping
that formatting logic in one place.
"""
from typing import AsyncGenerator, Optional
import json
import logging
from llm.engine import get_engine, DeepSeekEngine, DAWN_SYSTEM_PROMPT, CompletionResult
from llm.safety import AGENT_SAFETY_PROMPT, wrap_tool_output_for_model
from llm.identity import Identity, TrustTier
from tools.registry import get_registry, ToolRegistry
from tools.executor import execute_tool_call

logger = logging.getLogger(__name__)

DEFAULT_MAX_ITERATIONS = 500

# Phrases that claim a real-world action was taken. If these appear in a
# "final answer" (i.e. a response with no accompanying tool_call), the model
# is describing an action it didn't actually perform via any tool — DeepSeek
# occasionally does this instead of emitting a real tool_call. We can't fix
# the underlying model behavior, but we can refuse to silently accept the
# claim as fact and force a self-correction instead of letting it poison
# conversation history.
ACTION_CLAIM_PHRASES = [
    "i ran", "i executed", "i've run", "i have run", "i created", "i've created",
    "i have created", "i wrote", "i've written", "i have written", "i deleted",
    "i've deleted", "i have deleted", "i cloned", "i've cloned", "i committed",
    "i've committed", "i installed", "i've installed", "i searched", "i've searched",
    "i modified", "i've modified", "i updated the file", "i saved",
]


def _claims_unverified_action(text: str) -> bool:
    lowered = text.lower()
    return any(phrase in lowered for phrase in ACTION_CLAIM_PHRASES)


def build_agent_messages(user_message: str, history: list[dict]) -> list[dict]:
    """
    Agent-mode message builder. Unlike llm.engine.build_messages(), this does
    NOT inject knowledge-graph context up front — the agent instead calls the
    knowledge_graph tool (tools/knowledge_graph.py, wrapping llm.tools.build_context
    and the same memory lookup routers/chat.py uses) on demand. Kept separate
    deliberately so agent runs don't pay for a graph traversal on every single
    turn regardless of whether the task needs it.

    v37.0: Injects sub-agent descriptions so the supervisor knows when to delegate.
    """
    # Build base system prompt
    system = (
        DAWN_SYSTEM_PROMPT
        + "\n\nYou have access to tools for working with files, git repositories, "
          "web search, and installing new capabilities inside a sandboxed workspace. "
          "Use them when the task requires reading, writing, or inspecting real "
          "files or repositories — don't guess at contents you haven't actually read."
        + "\n\nWhen asked to visualize, chart, graph, or plot something, gather the "
          "underlying data first (e.g. via the knowledge_graph tool), then call "
          "create_chart with that data rather than describing a chart in words or "
          "claiming you can't produce visuals — you can, via that tool."
        + "\n\nBefore answering questions about Solomon, his projects, past decisions, "
          "or anything that might already be recorded, call the knowledge_graph tool "
          "first (search for topics/entities, recall for personal facts and "
          "preferences) rather than relying only on conversation history or "
          "guessing — DAWN's knowledge graph and memory may already have the answer."
    )

    # v37.0: Inject sub-agent descriptions for delegation awareness
    try:
        from slack_bot.sub_agents.registry import get_sub_agent_registry
        registry = get_sub_agent_registry()
        agent_descriptions = registry.agent_descriptions()
        if agent_descriptions:
            system += agent_descriptions
            system += (
                "\n\nWhen a task falls clearly into one of these specialist domains, "
                "use the delegate_to_subagent or delegate_parallel tools to hand off "
                "the work. The sub-agent will handle the details and return the result. "
                "This is more efficient than doing everything yourself."
            )
    except Exception as e:
        logger.debug(f"Could not load sub-agent descriptions: {e}")

    system += "\n" + AGENT_SAFETY_PROMPT

    messages = [{"role": "system", "content": system}]
    for turn in history[-10:]:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})
    return messages


async def _execute_tool_calls(
    result: CompletionResult,
    messages: list[dict],
    registry: ToolRegistry,
    allowed_names: set[str],
    engine: DeepSeekEngine,
    identity: Identity,
) -> AsyncGenerator[dict, None]:
    """
    Runs every tool call in `result`, yielding tool_call/tool_result events
    and appending the corresponding messages to `messages` in place. Shared
    by both the normal loop path and the post-re-prompt path so the two
    don't drift out of sync.
    """
    messages.append(engine.assistant_tool_call_message(result.content, result.tool_calls))

    for call in result.tool_calls:
        yield {"type": "tool_call", "name": call.name, "args": call.args}

        if "__parse_error__" in call.args:
            error = (
                f"Your tool call arguments for '{call.name}' were not valid JSON "
                f"({call.args['__parse_error__']}). This usually happens with long "
                f"multi-line string values containing quotes. Re-emit the call with "
                f"the 'content' argument base64-encoded to avoid escaping issues."
            )
            yield {"type": "tool_result", "name": call.name, "success": False, "output": None, "error": error}
            messages.append(engine.tool_result_message(
                tool_call_id=call.id,
                tool_name=call.name,
                result_json=json.dumps({"success": False, "output": None, "error": error, "metadata": {}}),
            ))
            continue
        
        # Defense in depth: even though disallowed tools weren't offered in
        # tool_specs, don't trust that the model can't hallucinate a call to
        # one anyway — re-check authorization at execution time.
        if call.name not in allowed_names:
            logger.warning(f"Identity {identity.key_id} attempted disallowed tool '{call.name}'")
            error = f"Not authorized to use tool '{call.name}'."
            yield {"type": "tool_result", "name": call.name, "success": False, "output": None, "error": error}
            messages.append(engine.tool_result_message(
                tool_call_id=call.id,
                tool_name=call.name,
                result_json=json.dumps({"success": False, "output": None, "error": error, "metadata": {}}),
            ))
            continue

        tool_result = await execute_tool_call(registry, call.name, call.args)

        yield {
            "type": "tool_result",
            "name": call.name,
            "success": tool_result.success,
            "output": tool_result.output,
            "error": tool_result.error,
        }

        wrapped = dict(tool_result.to_dict())
        if wrapped.get("output") is not None:
            wrapped["output"] = wrap_tool_output_for_model(call.name, json.dumps(wrapped["output"]))

        messages.append(engine.tool_result_message(
            tool_call_id=call.id,
            tool_name=call.name,
            result_json=json.dumps(wrapped),
        ))


async def run_agent_loop(
    user_message: str,
    identity: Identity,
    history: Optional[list[dict]] = None,
    max_iterations: int = DEFAULT_MAX_ITERATIONS,
) -> AsyncGenerator[dict, None]:
    """
    Runs the agent loop, yielding event dicts as it goes:
      {"type": "thinking", "content": "..."}
      {"type": "tool_call", "name": ..., "args": ...}
      {"type": "tool_result", "name": ..., "success": ..., "output": ...}
      {"type": "warning", "content": "..."}         # suspected fabricated action claim
      {"type": "token", "content": "..."}          # only on the final answer
      {"type": "done", "content": "...", "iterations": N}
      {"type": "error", "content": "..."}

    `identity` determines which tools are even offered to the model — see
    llm/identity.py. This does not replace the consequence/harm reasoning
    in AGENT_SAFETY_PROMPT, which applies regardless of identity tier.
    """
    engine = get_engine()
    registry = get_registry()

    engine = get_engine()
    registry = get_registry()

    if not isinstance(engine, DeepSeekEngine):
        yield {"type": "error", "content": (
            "Agent/tool workflows currently require LLM_MODE=deepseek — "
            "tool-calling is not yet validated for the local model."
        )}
        return

    def _current_tools() -> tuple[set[str], list[dict]]:
        """
        Re-snapshot allowed tool names + specs from the live registry.
        Must be called fresh after any tool execution — install_skill
        mutates the registry in place mid-loop (see skills/installer.py),
        so a stale snapshot taken once at the top would never see a
        newly installed skill, causing the model to be offered (or to
        hallucinate) a tool name this snapshot doesn't yet recognize.
        """
        all_tools = registry.list_tools()
        if not all_tools:
            return set(), []
        names = set(identity.allowed_tools([t.name for t in all_tools]))
        specs = [t.spec() for t in all_tools if t.name in names]
        return names, specs

    allowed_names, tool_specs = _current_tools()
    if not allowed_names:
        yield {"type": "error", "content": "No tools are registered, or this identity is not authorized to use any."}
        return

    messages = build_agent_messages(user_message, history or [])
    
    yield {"type": "thinking", "content": "Working on it..."}

    for iteration in range(1, max_iterations + 1):
        try:
            result = await engine.complete_with_tools(messages, tools=tool_specs)
        except Exception as e:
            logger.exception("engine.complete_with_tools failed")
            yield {"type": "error", "content": f"LLM call failed: {e}"}
            return

        if result.wants_tool_call:
            async for event in _execute_tool_calls(result, messages, registry, allowed_names, engine, identity):
                yield event
            allowed_names, tool_specs = _current_tools()
            continue  # get another completion now that tool results are in history

        # No tool call this turn — this is either a genuine final answer, or
        # the model describing an action it never actually took. Check before
        # trusting it.
        if _claims_unverified_action(result.content):
            logger.warning(
                "Model's final answer claims an action was taken with no "
                "tool_call this turn — likely fabrication. Re-prompting once."
            )
            messages.append({"role": "assistant", "content": result.content})
            messages.append({
                "role": "user",
                "content": (
                    "You described taking an action (creating, writing, deleting, "
                    "running, cloning, searching, etc.) but did not call any tool "
                    "this turn. You have not actually done this yet. If the task "
                    "requires it, call the appropriate tool now. If you were just "
                    "describing what you would do, say so plainly instead of "
                    "stating it as something already done."
                ),
            })
            yield {"type": "thinking", "content": "Double-checking that..."}

            try:
                result = await engine.complete_with_tools(messages, tools=tool_specs)
            except Exception as e:
                logger.exception("engine.complete_with_tools failed on re-prompt")
                yield {"type": "error", "content": f"LLM call failed: {e}"}
                return

            if result.wants_tool_call:
                async for event in _execute_tool_calls(result, messages, registry, allowed_names, engine, identity):
                    yield event
                allowed_names, tool_specs = _current_tools()
                continue  # back to the top for another completion

            if _claims_unverified_action(result.content):
                # Still fabricating after a direct correction — surface this
                # clearly rather than silently returning it as fact.
                yield {"type": "warning", "content": (
                    "This answer may describe an action that wasn't actually "
                    "performed via a tool. Treat it with caution and verify directly."
                )}

        yield {"type": "token", "content": result.content}
        yield {"type": "done", "content": result.content, "iterations": iteration}
        return

    yield {
        "type": "iteration_limit",
        "content": f"Reached max iterations ({max_iterations}) without a final answer.",
    }
