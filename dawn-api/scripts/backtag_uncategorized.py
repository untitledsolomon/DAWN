"""
DAWN Back-Tagging Script
========================
Re-tags all nodes currently tagged "uncategorized" (or with no tags at all)
against an expanded set of tags. Also creates new tags in the database
that are missing but needed for proper categorization.

Usage:
    python -m scripts.backtag_uncategorized

    Or via API trigger (if endpoint exists):
    POST /admin/backtag

What it does:
    1. Adds new tags to the `tags` table if they don't exist
    2. Queries all nodes with tags=["uncategorized"] or tags IS NULL
    3. Runs _auto_tag_content() on each node's title+body
    4. Attaches the matched tags via node_tags table
    5. Reports summary of what was tagged and what stayed uncategorized
"""

import asyncio
import logging
import sys
import os

# Ensure we can import from the dawn-api package
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("backtag")

# ─── New tags to add to the database ─────────────────────────────────────────
# These are tags that the auto-tagger needs to properly categorize documents
# like The 48 Laws of Power, Think and Grow Rich, and similar content.
NEW_TAGS = [
    {
        "name": "self-help",
        "description": "Self-help, personal development, psychology, philosophy, life strategy, success principles"
    },
    {
        "name": "philosophy",
        "description": "Philosophy, ethics, political theory, historical analysis, critical thinking"
    },
    {
        "name": "psychology",
        "description": "Psychology, human behavior, cognitive science, persuasion, influence"
    },
    {
        "name": "history",
        "description": "History, historical events, biographies, historical analysis, ancient civilizations"
    },
    {
        "name": "strategy",
        "description": "Strategy, tactics, game theory, military strategy, business strategy, competitive analysis"
    },
    {
        "name": "leadership",
        "description": "Leadership, management, executive skills, team building, organizational behavior"
    },
    {
        "name": "communication",
        "description": "Communication, negotiation, persuasion, public speaking, rhetoric, writing"
    },
    {
        "name": "economics",
        "description": "Economics, macroeconomics, microeconomics, economic theory, market analysis"
    },
    {
        "name": "politics",
        "description": "Politics, governance, political theory, international relations, policy"
    },
    {
        "name": "biography",
        "description": "Biography, memoir, autobiography, personal stories, life narratives"
    },
    {
        "name": "uncategorized",
        "description": "Default fallback tag for content that doesn't match any other category"
    },
]


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
        else:
            logger.debug(f"  ~ Tag already exists: '{tag_def['name']}'")

    return added


async def find_untagged_nodes():
    """Find all nodes that are uncategorized or have no tags."""
    import db.client as db

    db_client = db.get_db()

    # Method 1: Find nodes with "uncategorized" tag via node_tags join
    # We need to find the tag_id for "uncategorized"
    all_tags = await db.get_all_tags()
    uncat_tag = next((t for t in all_tags if t["name"] == "uncategorized"), None)
    uncat_tag_id = uncat_tag["id"] if uncat_tag else None

    # Get all node IDs that have the "uncategorized" tag
    uncategorized_node_ids = set()
    if uncat_tag_id:
        res = await asyncio.get_event_loop().run_in_executor(
            None,
            lambda: db_client.table("node_tags")
            .select("node_id")
            .eq("tag_id", uncat_tag_id)
            .execute()
        )
        uncategorized_node_ids = {row["node_id"] for row in (res.data or [])}

    # Method 2: Find nodes that have NO tags at all
    # Get all node IDs that appear in node_tags
    res = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: db_client.table("node_tags").select("node_id").execute()
    )
    tagged_node_ids = {row["node_id"] for row in (res.data or [])}

    # Get all active document nodes
    res = await asyncio.get_event_loop().run_in_executor(
        None,
        lambda: db_client.table("nodes")
        .select("id, title, body, type, source, source_ref")
        .in_("status", ["active", "stale"])
        .execute()
    )
    all_nodes = res.data or []

    # Separate into uncategorized and untagged
    uncategorized_nodes = []
    untagged_nodes = []

    for node in all_nodes:
        nid = node["id"]
        if nid in uncategorized_node_ids:
            uncategorized_nodes.append(node)
        elif nid not in tagged_node_ids:
            untagged_nodes.append(node)

    logger.info(f"  Found {len(uncategorized_nodes)} uncategorized nodes")
    logger.info(f"  Found {len(untagged_nodes)} untagged nodes (no tags at all)")

    return uncategorized_nodes + untagged_nodes


async def backtag_nodes(nodes: list[dict], batch_size: int = 50):
    """Run auto-tagging on each node and attach the matched tags."""
    # Import the auto-tagging function from the ingest router
    # We need to import it from the right place
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "routers"))

    # We'll import the function directly from ingest.py
    from routers.ingest import _auto_tag_content
    import db.client as db

    all_tags = await db.get_all_tags()
    tag_name_to_id = {t["name"]: t["id"] for t in all_tags}

    total = len(nodes)
    tagged_count = 0
    still_uncategorized = 0
    errors = 0

    for i, node in enumerate(nodes):
        if (i + 1) % 10 == 0:
            logger.info(f"  Progress: {i+1}/{total}")

        try:
            title = node.get("title", "") or ""
            body = node.get("body", "") or ""
            content = f"{title}\n\n{body}" if title else body

            if not content.strip():
                continue

            matched_tags = await _auto_tag_content(content, title)

            if matched_tags and matched_tags != ["uncategorized"]:
                # Attach the matched tags
                tag_ids = []
                for tag_name in matched_tags:
                    tid = tag_name_to_id.get(tag_name)
                    if tid:
                        tag_ids.append(tid)
                    else:
                        # Tag might have been just created — refresh
                        all_tags = await db.get_all_tags()
                        tag_name_to_id = {t["name"]: t["id"] for t in all_tags}
                        tid = tag_name_to_id.get(tag_name)
                        if tid:
                            tag_ids.append(tid)

                if tag_ids:
                    await db.attach_tags_batch([node["id"]], tag_ids)
                    tagged_count += 1
                    logger.info(f"    ✓ Tagged '{title[:60]}' as {matched_tags}")
            else:
                still_uncategorized += 1
                if (i + 1) % 50 == 0:
                    logger.info(f"    - Still uncategorized: '{title[:60]}'")

        except Exception as e:
            errors += 1
            logger.error(f"    ✗ Error tagging node {node.get('id', '?')} '{title[:60]}': {e}")

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

    # Step 2: Find untagged/uncategorized nodes
    logger.info("\n[Step 2] Finding untagged and uncategorized nodes...")
    nodes = await find_untagged_nodes()

    if not nodes:
        logger.info("  No untagged or uncategorized nodes found. Nothing to do.")
        return

    # Step 3: Back-tag them
    logger.info(f"\n[Step 3] Back-tagging {len(nodes)} nodes...")
    results = await backtag_nodes(nodes)

    # Step 4: Summary
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
            "\nNote: Some nodes remain uncategorized. This means their content "
            "didn't semantically match any of the available tags above the 0.35 "
            "threshold. You may want to:\n"
            "  1. Add more specific tags to the NEW_TAGS list in this script\n"
            "  2. Lower the threshold in _auto_tag_content() (currently 0.35)\n"
            "  3. Manually tag them via the UI"
        )


if __name__ == "__main__":
    asyncio.run(main())
