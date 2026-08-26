"""本地回归测试 stub：模拟认证、管理和成本接口。"""
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import argparse
import json
import re
from urllib.parse import parse_qs, urlparse

try:
    from .full_stub_data import *  # noqa: F403
except ImportError:
    from full_stub_data import *  # noqa: F403


def allocation_version(version):
    return {
        "id": version["number"],
        "version_no": version["number"],
        "effective_from": version["effective_from"],
        "effective_to": None,
        "status": "active",
        "change_reason": version["reason"],
        "created_by_name": "系统管理员",
        "rules": [
            {
                "category_id": row["id"],
                "category_code": row["code"],
                "category_name": row["name"],
                "driver": version["drivers"][row["id"]],
                "fallback_driver": "equal",
                "manual_ratio_json": None,
            }
            for row in COST_ROWS
        ],
    }


def ok(data, message="ok"):
    return {"code": "OK", "message": message, "request_id": "stub", "data": data}


def not_found():
    return {"code": "NOT_FOUND", "message": "stub route", "request_id": "stub", "data": None}


class Handler(BaseHTTPRequestHandler):
    def _send(self, payload, status=200, headers=None):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            return

    def _current_user(self):
        cookie = self.headers.get("Cookie", "")
        if "adp_e2e_session=viewer" in cookie:
            return LIMITED_USER
        if "adp_e2e_session=admin" in cookie:
            return ADMIN_USER
        return None

    def do_GET(self):
        request_url = urlparse(self.path)
        path = request_url.path
        if path == "/api/v1/health":
            return self._send(ok({"status": "ok", "environment": "e2e"}, "服务正常"))
        if path == "/api/v1/auth/csrf":
            return self._send(ok({"csrf_token": "stub-csrf-token"}))
        if path == "/api/v1/auth/me":
            user = self._current_user()
            if user is None:
                return self._send({"code": "UNAUTHENTICATED", "message": "未登录", "request_id": "stub", "data": None}, 401)
            return self._send(ok({"user": user, "next_path": "/workbench", "session": {"expires_at": "2099-01-01T00:00:00Z"}}))
        if path == "/api/v1/auth/register/options":
            return self._send(ok({"roles": ROLES, "areas": AREAS, "data_scopes": SCOPES}))
        if path == "/api/v1/auth/application":
            return self._send(ok({"application": None}))
        if path == "/api/v1/admin/options":
            return self._send(ok({"roles": ROLES, "areas": AREAS, "data_scopes": SCOPES}))
        if path == "/api/v1/admin/users":
            return self._send(ok({"items": MANAGED_USERS, "page": 1, "page_size": 20, "total": len(MANAGED_USERS), "has_next": False}))
        if path == "/api/v1/admin/applications":
            return self._send(ok({"items": APPLICATIONS, "page": 1, "page_size": 20, "total": len(APPLICATIONS), "has_next": False}))
        if path == "/api/v1/cost/structure":
            return self._send(ok({
                "period_start": "2026-01-01", "period_end": "2026-08-16",
                "total_amount": "672000.00", "direct_amount": "250000.00", "public_amount": "422000.00",
                "direct_share": "37.2024", "public_share": "62.7976",
                "confirmed_output_weight_jin": "0.000", "confirmed_income_amount": "0.00", "confirmed_profit_amount": "-672000.00",
                "unit_production_cost": None, "unit_cost_status": "output_not_connected",
                "source_fact_counts": {"warehouse": 0, "purchase": 0, "production": 0, "expense": 9, "asset": 0, "sales": 0},
                "source_quality": "legacy_import", "confirmed_entry_count": 9, "has_data": True,
                "categories": COST_ROWS,
            }))
        if path == "/api/v1/cost/entries":
            category_code = parse_qs(request_url.query).get("category_code", [None])[0]
            items = [entry for entry in COST_ENTRIES if category_code is None or entry["category_code"] == category_code]
            return self._send(ok({
                "items": items,
                "page": 1, "page_size": 20, "total": len(items), "has_next": False,
            }))
        if path == "/api/v1/cost/allocation-rules":
            query = parse_qs(request_url.query)
            if query.get("mode", [None])[0] == "latest":
                version = RULE_VERSIONS[-1]
            else:
                effective_at = query.get("effective_at", ["9999-12-31"])[0]
                candidates = [item for item in RULE_VERSIONS if item["effective_from"] <= effective_at]
                version = candidates[-1] if candidates else RULE_VERSIONS[0]
            return self._send(ok(allocation_version(version)))
        if path == "/api/v1/workbench/summary":
            return self._send(ok({
                "date_label": "2026-08-16",
                "availability": {"production": True},
                "kpis": {"ponds": 1, "active_batches": 1, "current_stock": 12000, "todo_open": 2},
                "pond_status": [{"status": "farming", "label": "养殖中", "count": 1}],
                "todos": [
                    {"id": 11, "title": "核验塘口档案 P-001", "type": "verify", "due_at": "2026-08-10 10:00:00", "overdue": True},
                    {"id": 12, "title": "核验入库单 IN-031", "type": "verify", "due_at": "2026-08-11 10:00:00", "overdue": True},
                ],
                "alerts": [{"id": 21, "title": "低库存预警：鲈鱼饲料", "level": "high", "created_at": "2026-08-16 08:30:00"}],
                "recent_batches": [],
            }))
        if path == "/api/v1/work-items":
            return self._send(ok({"items": WORK_ITEMS_STUB, "page": 1, "page_size": 100, "total": 2, "has_next": False}))
        if path == "/api/v1/notifications":
            return self._send(ok({"items": NOTIFICATIONS_STUB, "page": 1, "page_size": 100, "total": 1, "has_next": False}))
        if path == "/api/v1/master-data/ponds":
            return self._send(ok({"items": PONDS, "page": 1, "page_size": 20, "total": 1, "has_next": False}))
        if re.fullmatch(r"/api/v1/master-data/ponds/\d+", path):
            return self._send(ok({"record": PONDS[0]}))
        if path.startswith("/api/v1/master-data/areas"):
            return self._send(ok({"items": AREAS_STUB, "page": 1, "page_size": 100, "total": 2, "has_next": False}))
        if path.startswith("/api/v1/master-data/pond-groups"):
            return self._send(ok({"items": POND_GROUPS_STUB, "page": 1, "page_size": 100, "total": 1, "has_next": False}))
        if path == "/api/v1/warehouse/alerts":
            return self._send(ok({"items": ALERTS_STUB}))
        if path == "/api/v1/warehouse/warehouses":
            return self._send(ok({"items": []}))
        if any(re.fullmatch(pattern, path) for pattern in (
            r"/api/v1/production/[a-z-]+",
            r"/api/v1/master-data/[a-z-]+",
            r"/api/v1/purchase/[a-z-]+",
            r"/api/v1/sales/[a-z-]+",
            r"/api/v1/cost/[a-z-]+",
        )):
            return self._send(ok({"items": [], "page": 1, "page_size": 20, "total": 0, "has_next": False}))
        if path == "/api/v1/data-exchange/templates":
            return self._send(ok({"items": []}))
        return self._send(not_found())

    def do_POST(self):
        path = self.path.split("?")[0]
        if path == "/api/v1/auth/login":
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            user = LIMITED_USER if str(payload.get("identifier")) == LIMITED_USER["phone"] else ADMIN_USER
            session = "viewer" if user is LIMITED_USER else "admin"
            return self._send(
                ok({"user": user, "next_path": "/workbench", "session": {"expires_at": "2099-01-01T00:00:00Z"}}),
                headers={"Set-Cookie": f"adp_e2e_session={session}; Path=/; SameSite=Lax"},
            )
        if path == "/api/v1/master-data/ponds":
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            record = {**payload, "id": 2, "status": "draft", "row_version": 1, "version": 1,
                      "allowed_actions": ["view", "edit", "delete", "submit"], "pond_status": payload.get("pond_status", "build")}
            return self._send(ok({"record": record}))
        if re.fullmatch(r"/api/v1/warehouse/alerts/[^/]+/handle", path):
            return self._send(ok({"alert": {**ALERTS_STUB[0], "status": "handled", "allowed_actions": []}}))
        if path == "/api/v1/auth/register":
            return self._send(ok({
                "user": {"id": 99, "name": "新申请用户", "status": "pending"},
                "application": APPLICATIONS[0],
                "status": "pending", "next_path": "/auth/pending",
            }))
        if re.fullmatch(r"/api/v1/admin/users/\d+/reset-password", path):
            return self._send(ok(None))
        if re.fullmatch(r"/api/v1/admin/applications/\d+/(approve|reject)", path):
            return self._send(ok({"application": {**APPLICATIONS[0], "status": "approved"}}))
        return self._send(ok(None))

    def do_PATCH(self):
        path = self.path.split("?")[0]
        if re.fullmatch(r"/api/v1/master-data/ponds/\d+", path):
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            record = {**PONDS[0], **payload, "row_version": 4, "version": 4, "allowed_actions": ["view", "edit"]}
            return self._send(ok({"record": record}))
        if re.fullmatch(r"/api/v1/admin/applications/\d+/review", path):
            return self._send(ok({"application": {**APPLICATIONS[0], "status": "approved"}}))
        return self._send(ok(None))

    def do_PUT(self):
        path = self.path.split("?")[0]
        if path == "/api/v1/cost/allocation-rules":
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
            requested_rules = {item["category_id"]: item for item in payload.get("rules", [])}
            previous_drivers = RULE_VERSIONS[-1]["drivers"]
            version = {
                "number": RULE_VERSIONS[-1]["number"] + 1,
                "reason": payload.get("change_reason") or "更新成本分摊规则",
                "effective_from": payload.get("effective_from") or "2099-01-01",
                "drivers": {
                    row["id"]: requested_rules.get(row["id"], {}).get("driver", previous_drivers[row["id"]])
                    for row in COST_ROWS
                },
            }
            RULE_VERSIONS.append(version)
            return self._send(ok(allocation_version(version), "规则版本已保存"))
        if re.fullmatch(r"/api/v1/admin/users/\d+/grants", path):
            return self._send(ok({"grants": {"user_id": 2, "roles": ROLES[:1], "data_scopes": SCOPES[:1]}}))
        return self._send(ok(None))

    def do_DELETE(self):
        path = self.path.split("?")[0]
        if re.fullmatch(r"/api/v1/admin/users/\d+", path):
            return self._send(ok({"user": {"id": 3, "name": "王仓储", "phone": "13900000002"}}))
        return self._send(ok(None))

    def log_message(self, *_):
        return


def create_server(port=5001):
    """创建可并发处理 Playwright 请求的本地桩服务器。"""
    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5001)
    args = parser.parse_args()
    print(f"full stub listening on 127.0.0.1:{args.port}")
    create_server(args.port).serve_forever()
