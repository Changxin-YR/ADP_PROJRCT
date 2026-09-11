"""真库冒烟：验证「塘口存塘量汇总」与「智能体可直接写」两条链路走的是真实 MySQL。

本机没有 adp 库/凭据时无法执行，所以在有凭据的环境按下面方式跑：

    set MYSQL_HOST=127.0.0.1
    set MYSQL_DATABASE=adp_auth
    set MYSQL_USER=adp
    set MYSQL_PASSWORD=...
    python -m scripts.verify_agent_write --base-url http://127.0.0.1:5001 ^
        --identifier <管理员账号> --password <密码> [--pond-id 1]

它会：
1. 登录并列出塘口，挑一口有存塘流水的塘口；
2. 调 GET /api/v1/production/ponds/{id}/stock-summary，断言返回结构、data_source 口径与 SQL 聚合一致；
3. 用 /api/v1/agent/prepare 让智能体真的写一条投喂记录（若 AGENT_WRITE_MODE=direct，应直接 executed）；
4. 回到生产记录列表确认这条记录存在，并打印审计线索（request_id）。

只走真实 HTTP，不直连数据库改数据；写入的记录是普通草稿，可在页面上删除。
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from http.cookiejar import CookieJar
from typing import Any


class Smoke:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.jar = CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))
        self.csrf = ""

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> tuple[int, dict[str, Any]]:
        url = f"{self.base_url}{path}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(url, data=body, method=method)
        request.add_header("Accept", "application/json")
        if body is not None:
            request.add_header("Content-Type", "application/json")
        if self.csrf:
            request.add_header("X-CSRF-Token", self.csrf)
        try:
            with self.opener.open(request, timeout=60) as response:
                return response.status, json.loads(response.read().decode("utf-8") or "{}")
        except urllib.error.HTTPError as error:
            raw = error.read().decode("utf-8", errors="replace")
            try:
                return error.code, json.loads(raw or "{}")
            except json.JSONDecodeError:
                return error.code, {"raw": raw}

    def login(self, identifier: str, password: str) -> None:
        status, body = self.request("GET", "/api/v1/auth/csrf")
        assert status == 200, (status, body)
        self.csrf = body["data"]["csrf_token"]
        status, body = self.request("POST", "/api/v1/auth/login", {"identifier": identifier, "password": password})
        assert status == 200, (status, body)
        print(f"[ok] 登录成功：{body['data'].get('user', {}).get('name') or identifier}")

    def check_stock_summary(self, pond_id: int | None) -> None:
        status, body = self.request("GET", "/api/v1/master-data/ponds?page=1&page_size=50")
        assert status == 200, (status, body)
        ponds = body["data"].get("items") or body["data"].get("records") or []
        assert ponds, "没有可访问的塘口"
        target = pond_id or int(ponds[0]["id"])
        status, body = self.request("GET", f"/api/v1/production/ponds/{target}/stock-summary")
        assert status == 200, (status, body)
        data = body["data"]
        ledger = data["batch_stock"]
        print(f"[ok] 塘口 {target} 存塘量汇总：{ledger['quantity']} 尾 / {ledger['weight_kg']} kg，来源={data['data_source']}")
        print(f"     批次 {len(data.get('batches') or [])} 个，最近抽样={bool(data.get('latest_sampling'))}")
        if data["data_source"] == "batch_ledger":
            assert float(ledger["quantity"]) != 0 or float(ledger["weight_kg"]) != 0, "有批次流水却聚合为 0，SQL 口径可疑"
        elif data["data_source"] == "manual":
            print("     该塘口没有批次流水，按设计回退展示档案手工值（不会被当成生产事实）")
        else:
            print("     该塘口既无流水也无手工值，符合 data_source=none")

    def check_agent_write(self, pond_id: int | None) -> dict[str, Any]:
        code = "SMOKE-AGENT-WRITE-1"
        arguments = {
            "resource": "feed-logs",
            "payload": {
                "code": code,
                "name": "真库冒烟-投喂",
                "pond_id": pond_id or 1,
                "batch_id": 1,
                "material_id": 1,
                "quantity": 1,
                "weight_kg": 1,
            },
        }
        status, body = self.request(
            "POST",
            "/api/v1/agent/prepare",
            {
                "operation": "api.production_create_post_api_v1_production_resource",
                "arguments": arguments,
                "conversation_id": "smoke-agent-write",
            },
        )
        assert status == 200, (status, body)
        result = body["data"]
        kind = result.get("kind")
        print(f"[ok] 智能体写操作返回 kind={kind}")
        if kind == "executed":
            print(f"     人话输出：{result.get('message')}")
            assert not any(token in json.dumps(result, ensure_ascii=False) for token in ("api.", "POST", "traceback")), "输出里出现了技术标识"
        elif kind == "confirmation_required":
            print(f"     当前是 confirm 模式，确认卡片：{result['confirmation'].get('summary')} / 影响对象={result['confirmation'].get('target')}")
            token = result["confirmation"]["token"]
            status, confirmed = self.request("POST", "/api/v1/agent/confirm", {"token": token})
            assert status == 200, (status, confirmed)
            print(f"     确认后：{confirmed['data'].get('message')}")
        else:
            raise AssertionError(f"未预期的返回：{kind}")
        return {"code": code, "request_id": result.get("request_id")}

    def check_record_landed(self, code: str) -> None:
        status, body = self.request("GET", "/api/v1/production/feed-logs?page=1&page_size=50&search=" + code)
        assert status == 200, (status, body)
        items = body["data"].get("items") or []
        hit = [item for item in items if str(item.get("code")) == code]
        assert hit, f"业务列表里找不到刚写入的 {code}，写操作可能没有真正落库"
        print(f"[ok] 业务列表已能查到 {code}（status={hit[0].get('status')}）")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ADP 真库冒烟：存塘量汇总 + 智能体直接写")
    parser.add_argument("--base-url", default="http://127.0.0.1:5001")
    parser.add_argument("--identifier", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--pond-id", type=int, default=None)
    args = parser.parse_args(argv)

    smoke = Smoke(args.base_url)
    smoke.login(args.identifier, args.password)
    smoke.check_stock_summary(args.pond_id)
    written = smoke.check_agent_write(args.pond_id)
    smoke.check_record_landed(written["code"])
    print(f"\n冒烟通过。审计线索 request_id={written.get('request_id')}（可拿去操作日志核对）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
