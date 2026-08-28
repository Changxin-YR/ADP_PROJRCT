from backend.layers.features.purchase.purchase_payment_store import _sort as purchase_sort
from backend.layers.features.sales.sales_receipt_store import _sort as sales_sort


def test_server_sort_uses_whitelist_and_direction():
    assert purchase_sort("amount", "asc", {"amount": "p.amount"}, "p.id", "p.id") == "p.amount ASC,p.id DESC"
    assert sales_sort("amount;DROP TABLE users", "asc", {"amount": "r.amount"}, "r.due_date", "r.id") == "r.due_date ASC,r.id DESC"
