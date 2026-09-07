from __future__ import annotations

def specialized_permission(path: str, method: str, domain: str) -> str | None:
    """Map routes whose services use permissions finer than their URL domain."""
    if domain == "cost":
        if method == "GET": return "cost.view"
        if "allocation-rules" in path or path.rstrip("/").endswith("/allocations"): return "cost.allocation.manage"
        for kind, permission in (("assets", "asset"), ("entries", "entry"), ("expenses", "entry"), ("settlements", "settlement")):
            if f"/{kind}" in path:
                action = "verify" if "/verify" in path else "confirm" if "/confirm" in path else "reverse" if "/reverse" in path else "manage"
                return f"cost.{permission}.{action}"
    if domain == "data-exchange":
        if "/attachments" in path: return "attachment.manage"
        if "/exports" in path: return "data_exchange.export"
        if "/imports" in path and any(x in path for x in ("/preview", "/confirm", "/revoke")): return "data_exchange.import"
        return "data_exchange.view"
    if domain == "purchase":
        if "/payments" in path:
            return "finance.payable.view" if method == "GET" else "finance.payment.verify" if any(x in path for x in ("/verify", "/cancel", "/reverse")) else "finance.payment.manage"
        if "/payables" in path: return "finance.payable.view"
        if "/returns" in path:
            return "purchase.view" if method == "GET" else "purchase.return.verify" if any(x in path for x in ("/verify", "/cancel")) else "purchase.return.manage"
        return "purchase.view" if method == "GET" else "purchase.verify" if any(x in path for x in ("/approve", "/cancel")) else "purchase.manage"
    if domain == "sales":
        if "/receipts" in path:
            return "finance.receivable.view" if method == "GET" else "finance.receipt.verify" if any(x in path for x in ("/verify", "/cancel", "/reverse")) else "finance.receipt.manage"
        if "/receivables" in path: return "finance.receivable.view"
        if "/returns" in path:
            return "sales.view" if method == "GET" else "sales.return.verify" if any(x in path for x in ("/verify", "/cancel")) else "sales.return.manage"
        return "sales.view" if method == "GET" else "sales.verify" if any(x in path for x in ("/approve", "/cancel", "/verify")) else "sales.manage"
    return None
