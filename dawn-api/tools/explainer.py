"""
Explainer tool — generates animated, whiteboard-style HTML/SVG/JS explainer
artifacts for math and conceptual topics. Mirrors the create_chart tool pattern:
builds a self-contained HTML fragment via the LLM, validates it, and returns it
for the caller (routers/agent.py or routers/explainer.py) to persist.

The fragment is a single HTML string with inline CSS/JS, no external deps except
the CDN allowlist. It renders in a sandboxed iframe both inline in chat and on
the standalone artifact page.
"""
import json
import re
import logging
from typing import Optional
from tools.base import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# ── CDN allowlist ──────────────────────────────────────────────────────────────
ALLOWED_CDN_DOMAINS = {
    "cdnjs.cloudflare.com",
    "esm.sh",
    "cdn.jsdelivr.net",
    "unpkg.com",
    "fonts.googleapis.com",
    "fonts.gstatic.com",
}

# ── Forbidden APIs (sandbox safety) ────────────────────────────────────────────
# These catch both direct calls (eval(...)) and bracket-notation (window["eval"](...))
FORBIDDEN_PATTERNS = [
    r'\bfetch\s*\(',
    r'\bXMLHttpRequest\b',
    r'\bWebSocket\b',
    r'\blocalStorage\b',
    r'\bsessionStorage\b',
    # Catch eval( and window["eval"]( or globalThis["eval"](
    r'\[["\']eval["\']\]\s*\(',
    r'\beval\s*\(',
    # Catch Function( and new Function( and ["Function"]
    r'\[["\']Function["\']\]\s*\(',
    r'\bFunction\s*\(',
]

MAX_FRAGMENT_SIZE = 150_000  # 150KB

VALID_DIAGRAM_TYPES = {"flowchart", "structural", "illustrative"}


def _check_cdn_allowlist(html: str) -> Optional[str]:
    """Return an error message if a <script src> or <link href> points to a
    domain not on the allowlist, or None if everything is clean."""
    for tag_pattern in [r'<script\s+[^>]*src\s*=\s*"([^"]+)"',
                        r'<link\s+[^>]*href\s*=\s*"([^"]+)"']:
        for match in re.finditer(tag_pattern, html, re.IGNORECASE):
            url = match.group(1)
            m = re.match(r'https?://([^/]+)', url)
            if m:
                domain = m.group(1).lower()
                allowed = any(
                    domain == allowed_domain or domain.endswith("." + allowed_domain)
                    for allowed_domain in ALLOWED_CDN_DOMAINS
                )
                if not allowed:
                    return f"Blocked external resource: {url} (domain '{domain}' not in CDN allowlist)"
    return None


def _check_forbidden_apis(html: str) -> Optional[str]:
    """Return an error message if any forbidden API pattern is found."""
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, html):
            return f"Forbidden API call detected: {pattern}"
    return None


def _check_well_formed(html: str) -> Optional[str]:
    """Basic well-formedness check using a simple tag-balance approach.
    Returns None if tags are balanced, or an error message."""
    # Strip script/style content to avoid false positives
    stripped = re.sub(r'<(script|style)[^>]*>.*?</\1>', '', html, flags=re.DOTALL | re.IGNORECASE)
    # Strip self-closing tags
    stripped = re.sub(r'<[^>]+/>', '', stripped)
    # Strip HTML comments
    stripped = re.sub(r'<!--.*?-->', '', stripped, flags=re.DOTALL)

    opening = re.findall(r'<(\w+)[^>]*>', stripped)
    closing = re.findall(r'</(\w+)>', stripped)

    from collections import Counter
    open_count = Counter(opening)
    close_count = Counter(closing)

    void_elements = {'br', 'hr', 'img', 'input', 'meta', 'link', 'area',
                     'base', 'col', 'embed', 'source', 'track', 'wbr'}

    unbalanced = []
    for tag, count in open_count.items():
        if tag.lower() in void_elements:
            continue
        if count != close_count.get(tag, 0):
            unbalanced.append(f"<{tag}>: {count} open, {close_count.get(tag, 0)} close")

    if unbalanced:
        return f"Unbalanced tags: {'; '.join(unbalanced)}"
    return None


def _check_size(html: str) -> Optional[str]:
    """Return an error message if the fragment exceeds the size cap."""
    size = len(html.encode('utf-8'))
    if size > MAX_FRAGMENT_SIZE:
        return f"Fragment too large: {size:,} bytes (max {MAX_FRAGMENT_SIZE:,})"
    return None


def validate_explainer_fragment(html: str) -> tuple[bool, Optional[str]]:
    """Run all validation checks. Returns (is_valid, error_message)."""
    # 1. CDN allowlist
    err = _check_cdn_allowlist(html)
    if err:
        return False, err

    # 2. Forbidden APIs
    err = _check_forbidden_apis(html)
    if err:
        return False, err

    # 3. Well-formedness
    err = _check_well_formed(html)
    if err:
        return False, err

    # 4. Size cap
    err = _check_size(html)
    if err:
        return False, err

    return True, None


# ── System prompt for the LLM ──────────────────────────────────────────────────

EXPLAINER_SYSTEM_PROMPT = """You are generating a SINGLE self-contained HTML fragment for an animated, whiteboard-style explainer visualization. This is NOT a full webpage — it is a fragment that will be embedded in a sandboxed iframe.

## HARD CONSTRAINTS

1. **Fragment only** — No <!DOCTYPE>, <html>, <head>, or <body> tags. Output ONLY the inner HTML that would go inside <body>.

2. **Inline everything** — All CSS and JS must be inline. The only external resources allowed are from these CDN domains:
   - cdnjs.cloudflare.com
   - esm.sh
   - cdn.jsdelivr.net
   - unpkg.com
   - fonts.googleapis.com
   - fonts.gstatic.com

3. **Dark mode support** — Use CSS custom properties for all colors:
   - --text-primary (near-black in light, near-white in dark)
   - --text-secondary (medium gray)
   - --text-muted (light gray)
   - --surface-1 (white in light, dark gray in dark)
   - --surface-2 (light gray in light, slightly lighter dark in dark)
   - --accent (a vibrant color for highlights)
   - --accent-secondary (a second accent color)
   Define them in a :root block and override in @media (prefers-color-scheme: dark). Never hardcode hex colors except for physical-color scenes (fire=orange, water=blue, sky=light blue) which MUST also provide a dark-mode override.

4. **Animation** — Use CSS @keyframes (transform/opacity only) or a lightweight JS animation loop (requestAnimationFrame). No physics engines, no video encoding, no canvas unless the diagram genuinely needs pixel-level work.

5. **Math notation** — For math, load KaTeX from the CDN allowlist and render with katex.render(). Do NOT hand-draw glyphs in SVG.

6. **SVG + HTML controls** — Prefer SVG for the diagram/geometry and HTML controls (sliders, buttons, play/pause) layered around it. Mirror a Manim scene plus an interactive layer Manim doesn't have.

7. **Play/pause/replay** — Include a play/pause/replay control if the animation runs on a loop or timeline.

8. **Reduced motion** — Respect prefers-reduced-motion: wrap animation triggers so motion is opt-out, not forced.

9. **Dimensions** — Max viewBox width 680px equivalent (matches artifact/chat container), flexible height.

10. **No external content** — No copyrighted characters, no real people, no external image fetches.

11. **No forbidden APIs** — Do NOT use: fetch(), XMLHttpRequest, WebSocket, localStorage, sessionStorage, eval(), or Function() constructor.

## STYLE GUIDE

- Use clean, modern colors with good contrast
- Typography: system font stack, or load Inter/KaTeX from CDN
- Smooth transitions (0.3s-0.6s ease)
- Whiteboard feel: slightly rounded corners, subtle shadows, clean lines
- For flowcharts: use arrow markers, rounded boxes, decision diamonds
- For structural diagrams: containment boxes, nested layouts, connection lines
- For illustrative: visual metaphors, animated elements that build intuition

## OUTPUT FORMAT

Return ONLY the HTML fragment. No markdown fences, no explanation, no code block markers — just raw HTML that starts with a <div> or <svg> tag."""


class ExplainerTool(BaseTool):
    name = "create_explainer"
    description = (
        "Generate an animated, whiteboard-style explainer visualization for a math or "
        "conceptual topic. Use this when the user asks to 'explain' a concept, algorithm, "
        "or process and a visual/animated explanation would be more helpful than text. "
        "The result is a self-contained HTML/SVG/JS fragment with play/pause controls, "
        "dark mode support, and interactive elements like sliders."
    )
    input_schema = {
        "type": "object",
        "properties": {
            "topic": {
                "type": "string",
                "description": "The concept, algorithm, or process to explain visually.",
            },
            "diagram_type": {
                "type": "string",
                "enum": sorted(VALID_DIAGRAM_TYPES),
                "description": (
                    "flowchart: sequential steps, decision branches. "
                    "structural: containment / architecture. "
                    "illustrative: build intuition via visual metaphor (default for 'how does X work' / 'explain X')."
                ),
            },
            "title": {
                "type": "string",
                "description": "Short title for the explainer artifact.",
            },
            "description": {
                "type": "string",
                "description": "Optional 1-2 sentence description of what this explainer shows.",
            },
        },
        "required": ["topic", "diagram_type", "title"],
    }

    async def run(
        self,
        topic: str,
        diagram_type: str,
        title: str,
        description: Optional[str] = None,
    ) -> ToolResult:
        if diagram_type not in VALID_DIAGRAM_TYPES:
            return ToolResult(
                success=False,
                error=f"Invalid diagram_type '{diagram_type}'. Must be one of: {', '.join(sorted(VALID_DIAGRAM_TYPES))}.",
            )

        # Generate the explainer for real — this is the same code path the
        # /explainer/generate HTTP endpoint uses, so the agent tool call and
        # the direct API produce explainers identically.
        try:
            html_fragment, prompt_used = await _call_llm_for_explainer(topic, diagram_type)
        except Exception as e:
            logger.error(f"[explainer] Tool generation failed: {e}")
            return ToolResult(success=False, error=f"Explainer generation failed: {e}")

        is_valid, err = validate_explainer_fragment(html_fragment)
        if not is_valid:
            return ToolResult(success=False, error=f"Generated explainer failed validation: {err}")

        return ToolResult(
            success=True,
            output={
                "title": title,
                "description": description,
                "code": html_fragment,   # this is what routers/agent.py needs to see
                "prompt": prompt_used,
                "topic": topic,
                "diagram_type": diagram_type,
            },
            metadata={"artifact_type": "explainer", "diagram_type": diagram_type},
        )


async def _call_llm_for_explainer(
    topic: str,
    diagram_type: str,
    existing_code: Optional[str] = None,
    follow_up: Optional[str] = None,
) -> tuple[str, str]:
    """Call the LLM to generate an explainer HTML fragment.

    Returns (html_fragment, full_prompt) on success. Shared by the agent tool
    call (ExplainerTool.run) and the HTTP endpoints (routers/explainer.py) so
    both generate explainers identically. Raises on failure.
    """
    engine = get_engine()

    diagram_guide = {
        "flowchart": "Create a flowchart-style animation showing sequential steps and decision branches.",
        "structural": "Create a structural diagram showing containment, architecture, and relationships.",
        "illustrative": "Create an illustrative visual metaphor that builds intuition about the concept.",
    }

    user_prompt_parts = [f"Topic: {topic}"]
    user_prompt_parts.append(f"Diagram type: {diagram_type}")
    user_prompt_parts.append(f"Style guide: {diagram_guide.get(diagram_type, diagram_guide['illustrative'])}")

    if existing_code and follow_up:
        user_prompt_parts.append(f"\n\n--- EXISTING EXPLAINER CODE ---\n{existing_code}\n--- END EXISTING CODE ---")
        user_prompt_parts.append(f"\nFollow-up instruction: {follow_up}")
        user_prompt_parts.append("\nModify the existing code according to the follow-up instruction. Return the COMPLETE updated HTML fragment, not just the changes.")
    else:
        user_prompt_parts.append("\nGenerate a complete, self-contained HTML fragment following all constraints below.")

    user_prompt = "\n".join(user_prompt_parts)

    messages = [
        {"role": "system", "content": EXPLAINER_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    response = await engine.complete(messages)

    # Strip any markdown fences the LLM might add
    html = response.strip()
    html = re.sub(r'^```(?:html)?\s*\n', '', html)
    html = re.sub(r'\n```\s*$', '', html)
    html = html.strip()

    return html, user_prompt
