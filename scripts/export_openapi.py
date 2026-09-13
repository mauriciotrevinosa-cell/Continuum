"""Write the API's OpenAPI document where the web client generator reads it.

One script, used by developers and CI alike, so "regenerate the client" means
the same thing in both places (D-10):

    uv run python scripts/export_openapi.py
    pnpm --filter @continuum/web api:client

The document is written to ``apps/web/.openapi.json`` - inside the web
package, because ``pnpm --filter @continuum/web`` runs its scripts from that
directory and resolves relative paths against it. The file is a build input,
not source, and is ignored by Git; the generated ``schema.d.ts`` is what gets
committed and checked for drift.

Output is deterministic: keys sorted, fixed indentation, trailing newline.
Nothing here needs a running server, a database or a real data root.
"""

from __future__ import annotations

import json
import sys

from continuum_api import create_app

DEFAULT_OUTPUT = "apps/web/.openapi.json"


def main(argv: list[str]) -> int:
    output = argv[1] if len(argv) > 1 else DEFAULT_OUTPUT
    spec = create_app().openapi()
    text = json.dumps(spec, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    with open(output, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(text)
    print(f"wrote {output} ({len(spec.get('paths', {}))} paths)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
