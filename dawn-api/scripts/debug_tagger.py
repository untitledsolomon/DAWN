"""
Debug script: run the tagger on a specific 48 Laws chunk and print all scores.
Run: python -m scripts.debug_tagger
"""
import asyncio
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

async def main():
    from ingestion.tagger import HybridTagger
    
    tagger = HybridTagger()
    await tagger.refresh()
    
    # A 48 Laws chunk that's tagged uncategorized
    test_text = """that are seen and appear every hour make men much
more envied than those that are done in deed and are covered over with"""
    
    print("=== Tag thresholds ===")
    for name, thresh in sorted(tagger.tag_thresholds.items()):
        print(f"  {name}: {thresh:.4f}")
    
    print("\n=== Computing scores ===")
    if tagger.model is None:
        await tagger._load_model()
    
    doc_vec = tagger.model.encode(test_text[:2000], show_progress_bar=False)
    doc_norm = doc_vec / (__import__('numpy').linalg.norm(doc_vec) + 1e-10)
    
    scores = []
    for tag_name, tag_vec in tagger.tag_embeddings.items():
        if tag_name == "uncategorized":
            continue
        tag_norm = tag_vec / (__import__('numpy').linalg.norm(tag_vec) + 1e-10)
        sim = float(__import__('numpy').dot(doc_norm, tag_norm))
        scores.append((sim, tag_name))
    
    scores.sort(key=lambda x: -x[0])
    
    print(f"\nTop 10 scores:")
    for score, name in scores[:10]:
        threshold = tagger.tag_thresholds.get(name, 0.25)
        passes = "✓" if score >= threshold else "✗"
        print(f"  {passes} {name}: {score:.4f} (threshold: {threshold:.4f})")
    
    # Now run the actual tag method
    print("\n=== tag() result ===")
    result = await tagger.tag(text=test_text, title="", top_k=2, min_similarity=0.1, use_dynamic_thresholds=True)
    print(f"  Result: {result}")
    
    # Also test without dynamic thresholds
    result2 = await tagger.tag(text=test_text, title="", top_k=2, min_similarity=0.1, use_dynamic_thresholds=False)
    print(f"  Without dynamic thresholds: {result2}")

if __name__ == "__main__":
    asyncio.run(main())
