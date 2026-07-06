"""
DAWN Hybrid Semantic Tagger — Top-K + Adaptive Threshold + Dynamic Per-Tag Thresholds.

Three strategies, layered:

1. TOP-K (primary): Always returns the top K tags regardless of score.
   Guarantees every chunk gets tagged. K is configurable per call.

2. ADAPTIVE THRESHOLD (fallback guard): If the top tag's score is below
   a configurable floor (default 0.1), the chunk is considered garbage
   (page numbers, headers, OCR artifacts) and left uncategorized.

3. DYNAMIC PER-TAG THRESHOLDS (precision layer): Each tag learns its own
   threshold from historical tagging data. Tags that are naturally broad
   (e.g. "strategy") get a lower threshold; narrow tags (e.g. "economics")
   get a higher one. Stored in the tags table as `auto_threshold`.

   Learning rule (running average):
     new_threshold = 0.7 * old_threshold + 0.3 * score_of_last_match

   This means:
   - If a tag consistently matches at high scores, its threshold rises
     (it becomes more selective — only strong matches get through)
   - If a tag only matches at low scores, its threshold drops
     (it becomes more permissive — weak matches still get through)
   - Tags with no history default to 0.25

Usage:
    tagger = HybridTagger()
    tags = await tagger.tag("Some text content", top_k=2, min_similarity=0.1)
    # Returns ["strategy", "history"] or ["uncategorized"] if below floor

    # Force refresh tag embeddings after adding new tags:
    await tagger.refresh()

    # Update per-tag thresholds after a successful tagging run:
    await tagger.update_thresholds("strategy", 0.42)
"""

import logging
import numpy as np
from typing import Optional

logger = logging.getLogger(__name__)

# ── Tag descriptions (used when DB has none) ────────────────────────────────
_TAG_DESCRIPTIONS = {
    "crm": "Customer relationship management, sales, leads, contacts, deals",
    "payroll": "Payroll processing, salary, employee payments, PAYE, NSSF",
    "tax": "Tax compliance, VAT, income tax, URA, filing, deductions",
    "trading": "Financial trading, forex, stocks, algorithmic trading, MT5",
    "code": "Source code, programming, software development, scripts",
    "fashion": "Fashion, clothing, apparel, design, luxury brand, atelier",
    "business": "Business operations, strategy, SME, company management",
    "finance": "Finance, accounting, budgeting, financial reporting",
    "legal": "Legal, compliance, contracts, regulations, policy",
    "education": "Education, training, learning, documentation, guide",
    "health": "Health, medical, wellness, safety",
    "technology": "Technology, IT, infrastructure, systems, software",
    "marketing": "Marketing, advertising, social media, campaigns, branding",
    "hr": "Human resources, recruitment, employee management, staffing",
    "operations": "Operations, logistics, supply chain, processes",
    "self-help": "Self-help, personal development, psychology, philosophy, life strategy, success principles, motivation",
    "philosophy": "Philosophy, ethics, political theory, historical analysis, critical thinking, logic, morality",
    "psychology": "Psychology, human behavior, cognitive science, persuasion, influence, mental models",
    "history": "History, historical events, biographies, historical analysis, ancient civilizations, world history",
    "strategy": "Strategy, tactics, game theory, military strategy, business strategy, competitive analysis, power dynamics",
    "leadership": "Leadership, management, executive skills, team building, organizational behavior, decision making",
    "communication": "Communication, negotiation, persuasion, public speaking, rhetoric, writing, storytelling",
    "economics": "Economics, macroeconomics, microeconomics, economic theory, market analysis, trade",
    "politics": "Politics, governance, political theory, international relations, policy, power",
    "biography": "Biography, memoir, autobiography, personal stories, life narratives, historical figures",
    "uncategorized": "Default fallback tag for content that doesn't match any other category",
}

# Default per-tag threshold when no historical data exists
_DEFAULT_THRESHOLD = 0.25

# Floor: below this, the chunk is considered garbage
_ABSOLUTE_FLOOR = 0.1

# Learning rate for updating per-tag thresholds
_THRESHOLD_LEARNING_RATE = 0.3


class HybridTagger:
    """Hybrid semantic tagger with Top-K, adaptive threshold, and dynamic per-tag thresholds."""

    def __init__(self):
        self.model = None
        self.tag_embeddings: dict[str, np.ndarray] = {}
        self.tag_defs: dict[str, str] = {}       # name -> description
        self.tag_thresholds: dict[str, float] = {}  # name -> learned threshold
        self.tag_ids: dict[str, str] = {}         # name -> db id
        self._cache_key: Optional[frozenset] = None

    # ── Public API ──────────────────────────────────────────────────────────

    async def tag(
        self,
        text: str,
        title: str = "",
        top_k: int = 2,
        min_similarity: float = _ABSOLUTE_FLOOR,
        use_dynamic_thresholds: bool = True,
    ) -> list[str]:
        """Tag text using hybrid strategy.

        Args:
            text: The content to tag.
            title: Optional title (prepended to text).
            top_k: Number of top tags to return (default 2).
            min_similarity: Absolute floor below which content is uncategorized.
            use_dynamic_thresholds: If True, applies per-tag learned thresholds
                                    as an additional filter on top of top-k.

        Returns:
            List of tag names, e.g. ["strategy", "history"].
            Returns ["uncategorized"] if nothing passes the floor.
        """
        content = f"{title}\n{text}" if title else text
        content = content.strip()
        if not content or len(content) < 20:
            return ["uncategorized"]

        # Lazy-load model
        if self.model is None:
            await self._load_model()

        # Ensure tag embeddings are loaded
        if not self.tag_embeddings:
            await self.refresh()

        if not self.tag_embeddings:
            return ["uncategorized"]

        # Embed content
        try:
            doc_vec = self.model.encode(content[:2000], show_progress_bar=False)
        except Exception as e:
            logger.error(f"Tagger encoding failed: {e}")
            return ["uncategorized"]

        # Compute similarities — EXCLUDE "uncategorized" from scoring
        # so it can never win against a legitimate tag.
        doc_norm = doc_vec / (np.linalg.norm(doc_vec) + 1e-10)
        scores: list[tuple[float, str]] = []
        for tag_name, tag_vec in self.tag_embeddings.items():
            if tag_name == "uncategorized":
                continue
            tag_norm = tag_vec / (np.linalg.norm(tag_vec) + 1e-10)
            sim = float(np.dot(doc_norm, tag_norm))
            scores.append((sim, tag_name))

        # Sort descending by score
        scores.sort(key=lambda x: -x[0])

        # ── Strategy 1: Top-K ──────────────────────────────────────────────
        top_tags = scores[:top_k]

        # ── Strategy 2: Adaptive floor ─────────────────────────────────────
        # If even the top tag is below the absolute floor, it's garbage
        if top_tags[0][0] < min_similarity:
            return ["uncategorized"]

        # ── Strategy 3: Dynamic per-tag thresholds ─────────────────────────
        if use_dynamic_thresholds and self.tag_thresholds:
            matched = []
            for score, tag_name in top_tags:
                threshold = self.tag_thresholds.get(tag_name, _DEFAULT_THRESHOLD)
                if score >= threshold:
                    matched.append(tag_name)
            if matched:
                return matched
            # If dynamic thresholds filtered everything out, fall back to
            # the single best match (better than uncategorizing good content)
            return [top_tags[0][1]]

        # Without dynamic thresholds, just return top-k
        return [name for _, name in top_tags]

    async def refresh(self):
        """Reload tags from DB and recompute embeddings.

        Call this after adding new tags to the database.
        """
        import db.client as db

        # Fetch all tags from DB
        try:
            all_tags = await db.get_all_tags()
        except Exception:
            all_tags = []

        # Build tag definitions
        tag_defs: dict[str, str] = {}
        tag_ids: dict[str, str] = {}
        for t in all_tags:
            name = t.get("name", "").lower().strip()
            desc = t.get("description") or _TAG_DESCRIPTIONS.get(name, "")
            threshold = t.get("auto_threshold")
            if name:
                tag_defs[name] = desc
                tag_ids[name] = t["id"]
                if threshold is not None:
                    self.tag_thresholds[name] = float(threshold)
                elif name not in self.tag_thresholds:
                    self.tag_thresholds[name] = _DEFAULT_THRESHOLD

        # Fall back to built-in descriptions if DB has no tags
        if not tag_defs:
            tag_defs = dict(_TAG_DESCRIPTIONS)
            tag_ids = {}

        self.tag_defs = tag_defs
        self.tag_ids = tag_ids

        # Compute embeddings
        if self.model is None:
            await self._load_model()

        if self.model:
            tag_texts = [
                f"{name}: {desc}" if desc else name
                for name, desc in tag_defs.items()
            ]
            try:
                tag_vecs = self.model.encode(tag_texts, show_progress_bar=False)
                self.tag_embeddings = {
                    name: vec for name, vec in zip(tag_defs.keys(), tag_vecs)
                }
            except Exception as e:
                logger.error(f"Tag embedding refresh failed: {e}")

    async def update_threshold(self, tag_name: str, match_score: float):
        """Update a tag's dynamic threshold using running average.

        Called after a successful tag match to gradually tune selectivity.

        new_threshold = (1 - lr) * old_threshold + lr * match_score

        Where lr = _THRESHOLD_LEARNING_RATE (0.3).
        """
        old = self.tag_thresholds.get(tag_name, _DEFAULT_THRESHOLD)
        new = (1 - _THRESHOLD_LEARNING_RATE) * old + _THRESHOLD_LEARNING_RATE * match_score
        self.tag_thresholds[tag_name] = new

        # Persist to DB if we have the tag ID
        tag_id = self.tag_ids.get(tag_name)
        if tag_id:
            try:
                import db.client as db
                db_client = db.get_db()
                await db._async_execute(
                    lambda: db_client.table("tags")
                    .update({"auto_threshold": round(new, 4)})
                    .eq("id", tag_id)
                    .execute()
                )
            except Exception as e:
                logger.debug(f"Failed to persist threshold for '{tag_name}': {e}")

    async def get_thresholds(self) -> dict[str, float]:
        """Return current per-tag thresholds (for diagnostics)."""
        return dict(self.tag_thresholds)

    # ── Internal ────────────────────────────────────────────────────────────

    async def _load_model(self):
        try:
            from llm.embeddings import get_embedding_model
            self.model = get_embedding_model()
        except Exception as e:
            logger.warning(f"Tagger model load failed: {e}")
            self.model = None
