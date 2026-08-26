from backend.app import create_app
from fake_auth_store import FakeAuthStore
from test_auth_api import _csrf, _settings


def test_mobile_registration_returns_bearer_token_only_for_mobile_client() -> None:
    store = FakeAuthStore()
    client = create_app(_settings(), store=store).test_client()
    payload = {
        "name": "注册申请人",
        "password": "FarmPass9!",
        "confirm_password": "FarmPass9!",
        "desired_role_id": 1,
        "area_id": 1,
        "application_note": "移动端注册",
    }

    web = client.post(
        "/api/v1/auth/register",
        json={**payload, "phone": "13800000011"},
        headers={"X-CSRF-Token": _csrf(client)},
    )
    assert web.status_code == 201
    assert "token" not in web.get_json()["data"]["session"]

    mobile = client.post(
        "/api/v1/auth/register",
        json={**payload, "phone": "13800000012"},
        headers={"X-CSRF-Token": _csrf(client), "X-ADP-Client": "mobile"},
    )
    assert mobile.status_code == 201
    assert mobile.get_json()["data"]["session"]["token"]
