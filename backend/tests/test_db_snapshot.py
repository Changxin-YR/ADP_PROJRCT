from backend.tests.helpers.db_snapshot import compare_snapshots, normalize_snapshot


def test_snapshot_business_keys_make_row_order_deterministic() -> None:
    left = {"ponds": [{"code": "P-2", "name": "二号"}, {"code": "P-1", "name": "一号"}]}
    right = {"ponds": [{"code": "P-1", "name": "一号"}, {"code": "P-2", "name": "二号"}]}

    assert compare_snapshots(left, right, business_keys={"ponds": ("code",)})
    assert normalize_snapshot(left, business_keys={"ponds": ("code",)})["ponds"][0]["code"] == "P-1"
