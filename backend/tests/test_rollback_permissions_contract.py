from pathlib import Path


def test_blue_green_rollback_checks_legacy_role_permissions_before_switching_traffic() -> None:
    script = Path("deploy/rollback-blue-green.sh").read_text(encoding="utf-8")

    assert "auth.review" in script
    assert "auth.user.manage" in script
    assert "breed_manager" in script
    assert "MYSQL_DATABASE" in script
    assert script.index("auth.review") < script.index("mv -f -- \"$temporary\" \"$NGINX_LIVE\"")
