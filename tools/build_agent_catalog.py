from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app import app  # noqa: E402
from backend.layers.features.agent.agent_tool_registry import build_agent_catalog, build_registry  # noqa: E402


def build() -> dict[str, object]:
    catalog = build_agent_catalog(app, build_registry())
    target = ROOT / "docs" / "api" / "agent-tool-coverage.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return catalog


if __name__ == "__main__":
    result = build()
    print(json.dumps(result, ensure_ascii=False))
