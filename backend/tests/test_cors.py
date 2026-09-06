from backend.config.settings import Settings
from backend.app import create_app


def test_configured_origin_gets_credentials_cors_headers():
    settings = Settings.from_env({
        "APP_ENV": "test",
        "FLASK_SECRET_KEY": "test-flask-secret",
        "CSRF_SECRET_KEY": "test-csrf-secret",
        "MYSQL_HOST": "127.0.0.1",
        "MYSQL_PORT": "3306",
        "MYSQL_DATABASE": "adp_test",
        "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test-password",
        "SESSION_COOKIE_SECURE": "true",
        "ADP_CORS_ORIGINS": "null,http://localhost:5173",
    })
    client = create_app(settings).test_client()

    response = client.options(
        "/api/v1/health",
        headers={"Origin": "null", "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 204
    assert response.headers["Access-Control-Allow-Origin"] == "null"
    assert response.headers["Access-Control-Allow-Credentials"] == "true"
    assert client.application.config["SESSION_COOKIE_SAMESITE"] == "None"
