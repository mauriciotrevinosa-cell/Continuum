"""Write the published JSON Schemas under ``docs/schemas``.

    uv run python scripts/export_schemas.py

The chapter package schema is generated from its Pydantic model, so the
document and the validator can never disagree; the test suite fails when the
committed file drifts from the model. Output is deterministic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from continuum_production import package_json_schema

TARGETS = {"docs/schemas/chapter-package.v1.schema.json": package_json_schema}


def render(schema: dict[str, object]) -> str:
    return json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path.cwd()
    for relative, build in TARGETS.items():
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(render(build()), encoding="utf-8", newline="\n")
        print(f"wrote {relative}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
