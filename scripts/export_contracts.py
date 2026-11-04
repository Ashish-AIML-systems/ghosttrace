"""Export deterministic Pydantic JSON schemas and their aggregate hash."""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "code"))

from slam.contracts import CONTRACT_MODELS, CONTRACT_VERSION


def main() -> None:
    target = Path("contracts")
    target.mkdir(exist_ok=True)
    bundle = {
        "contract_version": CONTRACT_VERSION,
        "models": {model.__name__: model.model_json_schema() for model in CONTRACT_MODELS},
    }
    serialized = json.dumps(bundle, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    schema_path = target / "slam-contract-v1.schema.json"
    schema_path.write_text(serialized, encoding="utf-8", newline="\n")
    digest = hashlib.sha256(serialized.encode()).hexdigest()
    (target / "SCHEMA_SHA256").write_text(f"{digest}  {schema_path.name}\n", encoding="utf-8")
    (target / "CONTRACT_VERSION").write_text(f"{CONTRACT_VERSION}\n", encoding="utf-8")
    print(digest)


if __name__ == "__main__":
    main()
