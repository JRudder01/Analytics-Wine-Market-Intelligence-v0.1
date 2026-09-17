from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from public_data import refresh_all_public_data

if __name__ == "__main__":
    results = refresh_all_public_data()
    for r in results:
        print(r)
    # Do not fail the whole job when one government endpoint is temporarily unavailable.
    ok = sum(1 for r in results if r.get("status") == "ok")
    if ok == 0:
        raise SystemExit("No public sources refreshed successfully.")
