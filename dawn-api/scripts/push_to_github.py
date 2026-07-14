"""
Push DAWN code to GitHub with retry logic.
Run this when GitHub is having issues.
"""
import subprocess
import time
import sys

REPO_DIR = Path(__file__).resolve().parent.parent.parent  # DAWN-repo/

def push_with_retry(max_retries=10, delay=30):
    """Try to push to GitHub, retrying on failure."""
    for attempt in range(1, max_retries + 1):
        print(f"Push attempt {attempt}/{max_retries}...")
        result = subprocess.run(
            ["git", "-C", str(REPO_DIR), "push", "origin", "main"],
            capture_output=True, text=True, timeout=60
        )
        if result.returncode == 0:
            print("Push succeeded!")
            print(result.stdout)
            return True
        
        print(f"Push failed (attempt {attempt}): {result.stderr[:200]}")
        
        if "HTTP 500" in result.stderr or "500" in result.stderr:
            print(f"GitHub 500 error — retrying in {delay}s...")
            time.sleep(delay)
        else:
            print("Non-retryable error — giving up")
            print(result.stderr)
            return False
    
    print("Max retries reached — push failed")
    return False


if __name__ == "__main__":
    from pathlib import Path
    success = push_with_retry()
    sys.exit(0 if success else 1)
