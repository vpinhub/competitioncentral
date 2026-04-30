#!/usr/bin/env python3
"""
Rebuild json/list.json by scanning all JSON files in the json/ folder.
Files are sorted chronologically by the date embedded in their filename.
Run this any time list.json is out of sync with the actual files.
"""

import json
import os
import re

JSON_DIR  = "json"
LIST_JSON = os.path.join(JSON_DIR, "list.json")

DATE_RE = re.compile(r"(\d{4}-\d{2}-\d{2})")


def sort_key(filename: str) -> str:
    m = DATE_RE.search(filename)
    return m.group(1) if m else filename


def main() -> None:
    files = sorted(
        [
            f for f in os.listdir(JSON_DIR)
            if f.endswith(".json") and f != "list.json"
        ],
        key=sort_key,
    )

    entries = [{"name": f, "path": f"json/{f}"} for f in files]

    with open(LIST_JSON, "w") as fh:
        json.dump(entries, fh, indent=4)

    print(f"Wrote {len(entries)} entries to {LIST_JSON}")
    for e in entries:
        print(f"  {e['name']}")


if __name__ == "__main__":
    main()
