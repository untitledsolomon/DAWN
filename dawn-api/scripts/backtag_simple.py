"""
DAWN Back-Tagging Script — Simple Version
==========================================
A standalone script that:
  1. Adds new tags to the database (self-help, philosophy, psychology, etc.)
  2. Finds all nodes tagged "uncategorized" or with no tags
  3. Re-runs auto-tagging using the sentence-transformers model
  4. Attaches matched tags

This version re-implements the auto-tagging logic inline to avoid
import issues when running as a script.

Usage:
    cd dawn-api
    python -m scripts.backtag_simple
"""

import asyncio
import logging
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backtag")

# ─── New tags to add ──────────────────────────────────────────────────────────
NEW_TAGS = [
    {"name": "self-help", "description": "Self-help, personal development, psychology, philosophy, life strategy, success principles, motivation"},
    {"name": "philosophy", "description": "Philosophy, ethics, political theory, historical analysis, critical thinking, logic, morality"},
    {"name": "psychology", "description": "Psychology, human behavior, cognitive science, persuasion, influence, mental models"},
    {"name": "history", "description": "History, historical events, biographies, historical analysis, ancient civilizations, world history"},
    {"name": "strategy", "description": "Strategy, tactics, game theory, military strategy, business strategy, competitive analysis, power dynamics"},
    {"name": "leadership", "description": "Leadership, management, executive skills, team building, organizational behavior, decision making"},
    {"name": "communication", "description": "Communication, negotiation, persuasion, public speaking, rhetoric, writing, storytelling"},
    {"name": "economics", "description": "Economics, macroeconomics, microeconomics, economic theory, market analysis, trade"},
    {"name": "politics", "description": "Politics, governance, political theory, international relations, policy, power"},
    {"name": "biography", "description": "Biography, memoir, autobiography, personal stories, life narratives, historical figures"},
    {"name": "uncategorized", "description": "Default fallback tag for content that doesn't match any other category"},
]

# ─── Tag descriptions for semantic matching ───────────────────────────────────
# These are used when a tag exists but has no description in the DB.
TAG_DESCRIPTIONS = {
    "crm": "Customer relationship management, sales, leads, contacts, deals, pipeline",
    "payroll": "Payroll processing, salary, employee payments, PAYE, NSSF, Uganda payroll",
    "tax": "Tax compliance, VAT, income tax, URA, filing, deductions, Uganda tax",
    "trading": "Financial trading, forex, stocks, algorithmic trading, MT5, trading bot",
    "code": "Source code, programming, software development, scripts, coding",
    "fashion": "Fashion, clothing, apparel, design, luxury brand, atelier, mabruk",
    "business": "Business operations, strategy, SME, company management, entrepreneurship",
    "finance": "Finance, accounting, budgeting, financial reporting, investment",
    "legal": "Legal, compliance, contracts, regulations, policy, law",
    "education": "Education, training, learning, documentation, guide, tutorial",
    "health": "Health, medical, wellness, safety, healthcare",
    "technology": "Technology, IT, infrastructure, systems, software, engineering",
    "marketing": "Marketing, advertising, social media, campaigns, branding, growth",
    "hr": "Human resources, recruitment, employee management, staffing, hiring",
    "operations": "Operations, logistics, supply chain, processes, workflow",
    "regent": "Regent platform, digital systems, strategy firm, Kampala, Uganda",
    "ai": "AI models, agents, inference, training, machine learning, LLM",
    "software": "Software engineering, development, architecture, design patterns",
    "uganda": "Uganda-specific context, regulations, market, East Africa",
    "client": "Regent clients, engagements, projects, consulting",
    "jarvis": "Jarvis agent, OpenClaw, Paperclip stack, autonomous AI",
    "dawn": "DAWN system, knowledge graph, ingestion, embeddings",
    "personal": "Solomon personal preferences, habits, context, biography",
    "infrastructure": "VPS, Docker, Coolify, deployment, hosting, servers",
    "econ-sim": "EconSim C++ town economy simulator, SFML, game development",
    "mabruk": "Mabruk Atelier luxury fashion brand, clothing, design",
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


async def add_new_tags():
    """Add new tags to the database if they don't already exist."""
    import db.client as db

    existing_tags = await db.get_all_tags()
    existing_names = {t["name"] for t in existing_tags}

    added = 0
    for tag_def in NEW_TAGS:
        if tag_def["name"] not in existing_names:
            await db.create_tag(tag_def["name"], tag_def["description"])
            logger.info(f"  + Created tag: '{tag_def['name']}'")
            added += 1

    return added


async def find_nodes_to_tag():
    """Find all nodes that are uncategorized or have no tags at all."""
    import db.client as db

    db_client = db.get_db()

    # Get all tags
    all_tags = await db.get_all_tags()
    uncat_tag = next((t for t in all_tags if t["name"] == "uncategorized"), None)
    uncat_tag_id = uncat_tag["id"] if uncat_tag else None

    # Get all node_ids that have the "uncategorized" tag
    uncategorized_ids = set()
    if uncat_tag_id:
        res = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: db_client.table("node_tags")
            .select("node_id")
            .eq("tag_id", uncat_tag_id)
            .execute()
        )
        uncategorized_ids = {row["node_id"] for row in (res.data or [])}

    # Get all node_ids that have ANY tag
    res = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: db_client.table("node_tags").select("node_id").execute()
    )
    any_tag_ids = {row["node_id"] for row in (res.data or [])}

    # Get all active/stale nodes
    res = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: db_client.table("nodes")
        .select("id, title, body, type, source, source_ref")
        .in_("status", ["active", "stale"])
        .execute()
    )
    all_nodes = res.data or []

    # Separate
    to_tag = []
    for node in all_nodes:
        nid = node["id"]
        if nid in uncategorized_ids or nid not in any_tag_ids:
            to_tag.append(node)

    logger.info(f"  Found {len(to_tag)} nodes to re-tag "
                f"({len(uncategorized_ids)} uncategorized, "
                f"{len(all_nodes) - len(any_tag_ids)} untagged)")

    return to_tag


async def auto_tag_content(content: str, title: str = "",
                           top_n: int = 3, threshold: float = 0.35,
                           model=None, tag_embeddings: dict = None,
                           tag_name_to_id: dict = None) -> list[str]:
    """
    Re-implementation of _auto_tag_content for standalone use.
    Uses pre-loaded model and pre-computed tag embeddings for speed.
    """
    text = f"{title}\n\n{content}" if title else content
    text = text.strip()
    if not text:
        return ["uncategorized"]

    if model is None or tag_embeddings is None:
        return ["uncategorized"]

    try:
        doc_vec = model.encode(text[:2000], show_progress_bar=False)
    except Exception as e:
        logger.error(f"Encoding failed: {e}")
        return ["uncategorized"]

    doc_norm = doc_vec / (np.linalg.norm(doc_vec) + 1e-10)

    scores = []
    for tag_name, tag_vec in tag_embeddings.items():
        tag_norm = tag_vec / (np.linalg.norm(tag_vec) + 1e-10)
        sim = float(np.dot(doc_norm, tag_norm))
        scores.append((sim, tag_name))

    scores.sort(key=lambda x: -x[0])
    matched = [name for score, name in scores if score >= threshold][:top_n]

    if not matched:
        return ["uncategorized"]

    return matched


async def load_model_and_tags():
    """Load the sentence-transformers model and pre-compute tag embeddings."""
    from sentence_transformers import SentenceTransformer
    import db.client as db

    logger.info("  Loading sentence-transformers model (all-MiniLM-L6-v2)...")
    model = SentenceTransformer("all-MiniLM-L6-v2")
    logger.info("  Model loaded.")

    # Get all tags from DB
    all_tags = await db.get_all_tags()
    tag_name_to_id = {t["name"]: t["id"] for t in all_tags}

    # Build tag -> description map
    tag_defs = {}
    for t in all_tags:
        name = t["name"].lower().strip()
        desc = t.get("description") or TAG_DESCRIPTIONS.get(name, "")
        if name:
            tag_defs[name] = desc

    # If no tags in DB, use the built-in descriptions
    if not tag_defs:
        tag_defs = {k: v for k, v in TAG_DESCRIPTIONS.items() if k != "uncategorized"}

    logger.info(f"  Computing embeddings for {len(tag_defs)} tags...")
    tag_texts = [f"{name}: {desc}" if desc else name for name, desc in tag_defs.items()]
    tag_vecs = model.encode(tag_texts, show_progress_bar=True)
    tag_embeddings = {name: vec for name, vec in zip(tag_defs.keys(), tag_vecs)}

    return model, tag_embeddings, tag_name_to_id


async def backtag_nodes(nodes: list[dict], model, tag_embeddings: dict,
                        tag_name_to_id: dict, batch_size: int = 50):
    """Run auto-tagging on each node and attach matched tags."""
    import db.client as db

    total = len(nodes)
    tagged_count = 0
    still_uncategorized = 0
    errors = 0

    for i, node in enumerate(nodes):
        if (i + 1) % 10 == 0:
            logger.info(f"  Progress: {i+1}/{total} "
                        f"(tagged: {tagged_count}, uncat: {still_uncategorized}, err: {errors})")

        try:
            title = node.get("title", "") or ""
            body = node.get("body", "") or ""
            content = f"{title}\n\n{body}" if title else body

            if not content.strip():
                continue

            matched_tags = await auto_tag_content(
                content, title,
                model=model, tag_embeddings=tag_embeddings,
                tag_name_to_id=tag_name_to_id
            )

            if matched_tags and matched_tags != ["uncategorized"]:
                tag_ids = [tag_name_to_id[t] for t in matched_tags if t in tag_name_to_id]
                if tag_ids:
                    await db.attach_tags_batch([node["id"]], tag_ids)
                    tagged_count += 1
                    if tagged_count <= 5 or (i + 1) % 50 == 0:
                        logger.info(f"    ✓ Tagged '{title[:60]}' -> {matched_tags}")
            else:
                still_uncategorized += 1

        except Exception as e:
            errors += 1
            logger.error(f"    ✗ Error on node {node.get('id', '?')[:8]} '{title[:40]}': {e}")

    return {
        "total_processed": total,
        "tagged": tagged_count,
        "still_uncategorized": still_uncategorized,
        "errors": errors,
    }


async def main():
    logger.info("=" * 60)
    logger.info("DAWN Back-Tagging Script")
    logger.info("=" * 60)

    # Step 1: Add new tags
    logger.info("\n[Step 1] Adding new tags to database...")
    added = await add_new_tags()
    logger.info(f"  Done. Added {added} new tags.")

    # Step 2: Find nodes to tag
    logger.info("\n[Step 2] Finding untagged/uncategorized nodes...")
    nodes = await find_nodes_to_tag()

    if not nodes:
        logger.info("  No nodes to tag. Exiting.")
        return

    # Step 3: Load model and compute tag embeddings
    logger.info("\n[Step 3] Loading model and computing tag embeddings...")
    model, tag_embeddings, tag_name_to_id = await load_model_and_tags()

    # Step 4: Back-tag
    logger.info(f"\n[Step 4] Back-tagging {len(nodes)} nodes...")
    results = await backtag_nodes(nodes, model, tag_embeddings, tag_name_to_id)

    # Step 5: Summary
    logger.info("\n" + "=" * 60)
    logger.info("SUMMARY")
    logger.info("=" * 60)
    logger.info(f"  Total nodes processed:  {results['total_processed']}")
    logger.info(f"  Successfully tagged:    {results['tagged']}")
    logger.info(f"  Still uncategorized:    {results['still_uncategorized']}")
    logger.info(f"  Errors:                 {results['errors']}")
    logger.info("=" * 60)

    if results["still_uncategorized"] > 0:
        logger.info(
            "\nNote: Some nodes remain uncategorized. Their content didn't "
            "semantically match any tag above the 0.35 threshold.\n"
            "Options:\n"
            "  1. Add more specific tags to NEW_TAGS in this script\n"
            "  2. Lower the threshold (change threshold=0.35 in auto_tag_content)\n"
            "  3. Manually tag via the UI"
        )


if __name__ == "__main__":
    asyncio.run(main())
