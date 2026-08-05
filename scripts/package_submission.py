from __future__ import annotations

import argparse
import zipfile
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--archive", type=Path, default=Path("submission.zip"))
    args = parser.parse_args()
    files = sorted(args.output_dir.glob("EC_*.json"))
    expected = [f"EC_{i:03d}.json" for i in range(1, 51)]
    if [p.name for p in files] != expected:
        raise SystemExit("output directory must contain exactly EC_001.json through EC_050.json")
    with zipfile.ZipFile(args.archive, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in files:
            archive.write(path, f"output/{path.name}")
    print(f"created {args.archive} with {len(files)} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
