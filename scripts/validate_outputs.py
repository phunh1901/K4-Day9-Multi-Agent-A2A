from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.models import FinalCaseOutput
from src.tools.datastore import DataStore


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument("--data-dir", type=Path, default=Path("data"))
    args = parser.parse_args()
    paths = sorted(args.output_dir.glob("EC_*.json"))
    expected = [f"EC_{i:03d}.json" for i in range(1, 51)]
    names = [path.name for path in paths]
    if names != expected:
        raise SystemExit(f"expected exactly 50 outputs, found {names}")
    store = DataStore(args.data_dir)
    for path in paths:
        output = FinalCaseOutput.model_validate(json.loads(path.read_text(encoding="utf-8")))
        errors = output.validate_business_shape()
        errors.extend(f"invalid evidence {e}" for e in output.evidence_ids if not store.evidence_exists(e))
        if errors:
            raise SystemExit(f"{path}: {'; '.join(errors)}")
    print("validated 50 outputs")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
