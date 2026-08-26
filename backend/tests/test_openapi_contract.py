from __future__ import annotations

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
OPENAPI = ROOT / "api-docs" / "openapi.json"
HTTP_METHODS = {"get", "post", "put", "patch", "delete"}


def _openapi_path(rule: str) -> str:
    return re.sub(r"<(?:int|path):([^>]+)>|<([^>]+)>", lambda match: "{" + (match.group(1) or match.group(2)) + "}", rule)


def _load_spec() -> dict:
    return json.loads(OPENAPI.read_text(encoding="utf-8"))


def test_openapi_covers_every_registered_api_method(app):
    documented = {
        (path, method)
        for path, path_item in _load_spec()["paths"].items()
        for method in path_item
        if method in HTTP_METHODS
    }
    registered = {
        (_openapi_path(rule.rule), method.lower())
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/v1")
        for method in rule.methods - {"HEAD", "OPTIONS"}
    }
    assert documented == registered


def test_each_operation_has_stable_success_and_error_contracts():
    spec = _load_spec()
    for path, path_item in spec["paths"].items():
        for method, operation in path_item.items():
            if method not in HTTP_METHODS:
                continue
            assert operation["operationId"], f"{method.upper()} {path} lacks operationId"
            responses = operation["responses"]
            assert any(code.startswith("2") for code in responses), f"{method.upper()} {path} lacks success response"
            assert responses["default"]["$ref"] == "#/components/responses/ErrorResponse"


def test_examples_and_guides_do_not_contain_credentials():
    files = [OPENAPI, *sorted((ROOT / "docs" / "api" / "guides").glob("*.md"))]
    text = "\n".join(path.read_text(encoding="utf-8") for path in files)
    forbidden = [
        r"BEGIN (?:RSA |OPENSSH )?PRIVATE KEY",
        r"(?i)(?:password|secret|token)\s*[:=]\s*['\"]?(?!<|示例|your-|example-)[^\s'\"]{8,}",
        r"\bAKIA[0-9A-Z]{16}\b",
    ]
    assert not any(re.search(pattern, text) for pattern in forbidden)


def test_calling_guides_cover_enterprise_controls():
    guide_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted((ROOT / "docs" / "api" / "guides").glob("*.md"))
    )
    for topic in ("Cookie", "CSRF", "分页", "幂等", "版本冲突", "核验后只读", "附件", "调用顺序"):
        assert topic in guide_text
