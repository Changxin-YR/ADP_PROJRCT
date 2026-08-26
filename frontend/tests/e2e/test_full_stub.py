"""Playwright 全流程桩服务的最小回归测试。"""
from concurrent.futures import ThreadPoolExecutor
from http.cookiejar import CookieJar
from urllib.error import HTTPError
import json
from pathlib import Path
import sys
from threading import Thread
from urllib.request import HTTPCookieProcessor, Request, build_opener, urlopen

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parent))

from full_stub import create_server  # noqa: E402


def _json(url: str, *, payload: dict | None = None, opener=None) -> dict:
    body = None if payload is None else json.dumps(payload).encode()
    request = Request(url, data=body, headers={"Content-Type": "application/json"})
    open_request = urlopen if opener is None else opener.open
    with open_request(request, timeout=3) as response:
        return json.loads(response.read())


def test_full_stub_health_auth_and_concurrency() -> None:
    server = create_server(0)
    worker = Thread(target=server.serve_forever, daemon=True)
    worker.start()
    base_url = f"http://127.0.0.1:{server.server_port}/api/v1"
    try:
        with ThreadPoolExecutor(max_workers=4) as pool:
            health = list(pool.map(lambda _: _json(f"{base_url}/health"), range(8)))
        assert all(item["data"]["status"] == "ok" for item in health)

        authenticated = build_opener(HTTPCookieProcessor(CookieJar()))
        anonymous = build_opener(HTTPCookieProcessor(CookieJar()))
        login = _json(
            f"{base_url}/auth/login",
            payload={"identifier": "13800000000", "password": "test"},
            opener=authenticated,
        )
        assert login["data"]["next_path"] == "/workbench"
        assert _json(f"{base_url}/auth/me", opener=authenticated)["data"]["user"]["login_name"] == "admin"
        for path in (
            "production/batches",
            "production/feed-plans",
            "production/harvests",
            "master-data/materials",
            "master-data/customers",
            "warehouse/warehouses",
            "purchase/orders",
            "sales/orders",
            "sales/deliveries",
            "cost/expenses",
        ):
            assert _json(f"{base_url}/{path}", opener=authenticated)["data"]["items"] == []
        assert _json(f"{base_url}/data-exchange/templates", opener=authenticated)["data"]["items"] == []
        with pytest.raises(HTTPError) as error:
            _json(f"{base_url}/auth/me", opener=anonymous)
        assert error.value.code == 401
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=3)
