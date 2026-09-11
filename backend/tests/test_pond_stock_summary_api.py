from __future__ import annotations

from typing import Any

from backend.app import create_app
from backend.config.settings import Settings
from pond_stock_fixtures import FakePondStockStore, seeded_store
from fake_auth_store import FakeAuthStore


# 前端（PondListPage.vue / PondDetailPage.vue -> workbench.service.ts）与线上 nginx
# （rewrite ^/adp/api/(.*)$ /api/$1）都硬绑定这两个路径：任何改名或漏注册都会让线上直接 404。
STOCK_SUMMARY_RULES = {
    "/api/v1/production/ponds/stock-summary": "production.pond_stock_summaries",
    "/api/v1/production/ponds/<int:pond_id>/stock-summary": "production.pond_stock_summary",
}


def build_client(store: FakePondStockStore, permissions: list[str]) -> Any:
    auth = FakeAuthStore()
    account = auth.add_user(phone="13800000707", login_name="pond-summary-admin", password="Correct9!", status="active")
    account["permissions"] = permissions
    settings = Settings.from_env({
        "APP_ENV": "test", "FLASK_SECRET_KEY": "pond-summary-test", "CSRF_SECRET_KEY": "pond-summary-csrf",
        "MYSQL_HOST": "127.0.0.1", "MYSQL_DATABASE": "adp_test", "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test", "SESSION_COOKIE_SECURE": "false",
    })
    client = create_app(settings, store=auth, production_store=store).test_client()
    token = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    assert client.post("/api/v1/auth/login", json={"identifier": "pond-summary-admin", "password": "Correct9!"},
                       headers={"X-CSRF-Token": token}).status_code == 200
    return client


def test_pond_stock_summary_route_returns_contract_shape() -> None:
    client = build_client(seeded_store(), ["production.view"])

    response = client.get("/api/v1/production/ponds/10/stock-summary")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert data["pond_id"] == 10
    assert data["batch_stock"] == {"quantity": "1200.000", "weight_kg": "25.500"}
    assert data["data_source"] == "batch_ledger"
    assert data["latest_sampling"]["document_id"] == 9
    assert data["batches"][0]["batch_id"] == 1


def test_pond_stock_summary_route_rejects_missing_permission() -> None:
    client = build_client(seeded_store(), ["master_data.view"])

    response = client.get("/api/v1/production/ponds/10/stock-summary")

    assert response.status_code == 403
    assert response.get_json()["code"] == "FORBIDDEN"


def test_pond_stock_summary_list_route_supports_pond_ids() -> None:
    client = build_client(seeded_store(), ["production.view"])

    response = client.get("/api/v1/production/ponds/stock-summary?pond_ids=10,11")

    assert response.status_code == 200
    data = response.get_json()["data"]
    assert [item["pond_id"] for item in data["items"]] == [10, 11]
    assert data["total"] == 2


def test_pond_stock_summary_list_route_rejects_invalid_pond_ids() -> None:
    client = build_client(seeded_store(), ["production.view"])

    response = client.get("/api/v1/production/ponds/stock-summary?pond_ids=abc")



def build_app(store: FakePondStockStore) -> Any:
    settings = Settings.from_env({
        "APP_ENV": "test", "FLASK_SECRET_KEY": "pond-summary-test", "CSRF_SECRET_KEY": "pond-summary-csrf",
        "MYSQL_HOST": "127.0.0.1", "MYSQL_DATABASE": "adp_test", "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test", "SESSION_COOKIE_SECURE": "false",
    })
    return create_app(settings, store=FakeAuthStore(), production_store=store)


def test_stock_summary_routes_are_registered_in_url_map() -> None:
    """回归：存塘量汇总两条路由必须注册在 url_map 中，且只能通过 GET 命中。

    线上 404（code=NOT_FOUND「请求的资源不存在」）正是这两条规则缺失的表现：
    未登录访问已注册路由会先得到 401，只有路由不存在才会得到 404。
    """
    app = build_app(seeded_store())
    url_map = {str(rule.rule): rule.endpoint for rule in app.url_map.iter_rules()}

    for rule, endpoint in STOCK_SUMMARY_RULES.items():
        assert rule in url_map, f"存塘量汇总路由缺失（前端 /api/v1/... 会直接 404）：{rule}"
        assert url_map[rule] == endpoint, f"存塘量汇总路由 endpoint 被改名：{rule} -> {url_map[rule]}"

    sample_rules = [rule for rule in app.url_map.iter_rules() if str(rule.rule) in STOCK_SUMMARY_RULES]
    for rule in sample_rules:
        methods = set(rule.methods or ())
        assert "GET" in methods, f"存塘量汇总路由不再接受 GET：{rule.rule}"
        assert "POST" not in methods, f"存塘量汇总路由是只读查询，不应接受 POST：{rule.rule}"


def test_stock_summary_routes_win_over_generic_resource_rule() -> None:
    """回归：/ponds/stock-summary 不能被通用路由 /<resource> 或 /<resource>/<int:record_id> 抢走。

    production 蓝图里的 /<resource> 系列是通配路由，静态段必须优先匹配；
    否则列表页/详情页会退化成 404 或被通用 record 接口接管。
    """
    client = build_client(seeded_store(), ["production.view"])

    list_response = client.get("/api/v1/production/ponds/stock-summary?pond_ids=10,11")
    detail_response = client.get("/api/v1/production/ponds/10/stock-summary")

    assert list_response.status_code != 405
    assert detail_response.status_code != 405
    assert list_response.get_json()["code"] == "OK"
    assert detail_response.get_json()["code"] == "OK"


def test_stock_summary_routes_reject_non_read_methods_with_chinese_message() -> None:
    """回归：只读汇总路由写请求必须 405，且中文提示可读（不出现英文技术术语）。"""
    client = build_client(seeded_store(), ["production.view"])

    response = client.post("/api/v1/production/ponds/stock-summary", json={})

    assert response.status_code == 405
    body = response.get_json()
    assert body["code"] == "METHOD_NOT_ALLOWED"
    assert body["message"] == "请求方法不受支持"
