"""Keep the extension collector identical to the canonical packaged collector.

Default: read-only drift check. Use --write to update the generated extension copy.
No imports from the application, browsers, network access or model calls.
"""

import argparse
import shutil
from pathlib import Path


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="Copy canonical collector to extension"
    )
    args = parser.parse_args(argv)
    root = Path(__file__).resolve().parents[1]
    canonical = root / "src/agentic_web_demo/dashboard/static/capture_dom.js"
    generated = root / "extensions/page-capture/capture_dom.js"
    try:
        source = canonical.read_bytes()
        current = generated.read_bytes() if generated.exists() else None
        if source == current:
            print("Capture collectors match; no files changed.")
            return 0
        if not args.write:
            print(
                "Capture collector drift: edit the canonical dashboard collector, then run "
                "uv run --locked python scripts/sync_capture.py --write and review both files."
            )
            return 1
        shutil.copyfile(canonical, generated)
        print("Updated the generated extension collector from the canonical dashboard collector.")
        return 0
    except OSError:
        print("Cannot read/copy the collector files. Check the repository paths and permissions.")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
