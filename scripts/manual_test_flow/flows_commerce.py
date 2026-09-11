"""阶段 5-6：采购收货/应付/付款 与 出塘销售/应收/收款。"""
from __future__ import annotations

from datetime import date, datetime, timedelta

PREFIX = "MT2609"


class CommerceFlows:
    def purchase_and_payable(self) -> None:
        self.section("阶段 5：采购 → 收货 → 自动应付 → 付款")
        order = self.create("/api/v1/purchase/orders", {
            "code": f"{PREFIX}-PO-01", "name": "9月饲料采购", "supplier_id": self.ids["supplier"],
            "material_id": self.ids["material_FEED"], "warehouse_id": self.ids["warehouse"],
            "quantity": 200, "unit_price": 12.5, "expected_delivery_date": date.today().isoformat(),
            "due_date": (date.today() + timedelta(days=30)).isoformat(), "note": "自动验收",
        })
        self.ids["purchase_order"] = int(order["id"])
        self.expect_error(
            "反向：采购经办人自己审批被拒绝",
            lambda: self.writer.post(f"/api/v1/purchase/orders/{order['id']}/approve", {"expected_version": order["version"]}),
            status=403, code="SELF_APPROVAL_FORBIDDEN",
        )
        order = self.submit("/api/v1/purchase/orders", order)
        _, body = self.verifier.post(f"/api/v1/purchase/orders/{order['id']}/approve", {"expected_version": order["version"]})
        self.check("采购单换人审批通过", self.record_of(body)["status"] == "approved")

        receipt = self.create("/api/v1/warehouse/receipts", {
            "code": f"{PREFIX}-IN-01", "name": "饲料到货入库", "warehouse_id": self.ids["warehouse"],
            "material_id": self.ids["material_FEED"], "quantity": 200, "unit_cost": 12.5,
            "lot_no": f"{PREFIX}-LOT-FEED-01",
            "production_date": (date.today() - timedelta(days=10)).isoformat(),
            "expiry_date": (date.today() + timedelta(days=170)).isoformat(), "location": "A-01-01",
            "purchase_order_id": self.ids["purchase_order"],
            "happened_at": datetime.now().replace(microsecond=0).isoformat(),
        })
        self.ids["receipt"] = int(receipt["id"])
        receipt = self.advance("/api/v1/warehouse/receipts", receipt, evidence=True)
        self.check("入库单带凭据核验通过", receipt["status"] == "verified")
        # 退货需要引用核验后生成的物料批次（inventory_lot_id）
        _, body = self.writer.get(f"/api/v1/warehouse/receipts/{self.ids['receipt']}")
        detail = body.get("data", {}).get("record", {})
        if detail.get("inventory_lot_id"):
            self.ids["inventory_lot"] = int(detail["inventory_lot_id"])

        payable = self._payable_of_order()
        self.check("收货核验后自动生成应付", bool(payable))
        if not payable:
            return
        self.ids["payable"] = int(payable["id"])

        payment = self.create("/api/v1/purchase/payments", {
            "code": f"{PREFIX}-PAY-01", "name": "9月饲料货款（部分）", "payable_id": self.ids["payable"],
            "amount": 1500, "paid_at": date.today().isoformat(), "payment_method": "bank_transfer", "note": "自动验收",
        })
        self.check("付款带凭据核验通过", self.advance("/api/v1/purchase/payments", payment, evidence=True)["status"] == "verified")
        updated = self._payable_of_order()
        self.check(
            "应付余额按付款核销",
            bool(updated) and float(updated.get("balance") or 0) == 1000.0,
            f"余额 {updated.get('balance') if updated else '—'}",
        )

    def _payable_of_order(self) -> dict | None:
        _, body = self.writer.get("/api/v1/purchase/payables?page=1&page_size=100")
        for row in body["data"]["items"]:
            if int(row.get("purchase_order_id") or 0) == self.ids["purchase_order"]:
                self.ids["payable"] = int(row["id"])
                return row
        return None

    def sales_and_receivable(self) -> None:
        self.section("阶段 6：出塘 → 销售 → 交付 → 自动应收 → 收款")
        harvest = self.create("/api/v1/production/harvests", {
            "code": f"{PREFIX}-HV-01", "name": "1号塘首批起捕", "batch_id": self.ids["batch"],
            "pond_id": self.ids["pond1"], "quantity": 3000, "weight_kg": 450,
            "happened_at": datetime.now().replace(microsecond=0).isoformat(), "note": "销售交付",
        })
        self.ids["harvest"] = int(harvest["id"])
        self.check("出塘带凭据核验通过", self.advance("/api/v1/production/harvests", harvest, evidence=True)["status"] == "verified")

        order = self.create("/api/v1/sales/orders", {
            "code": f"{PREFIX}-SO-01", "name": "草鱼首批销售", "customer_id": self.ids["customer"],
            "pond_id": self.ids["pond1"], "batch_id": self.ids["batch"], "species": "草鱼",
            "quantity": 450, "unit": "kg", "unit_price": 16.8, "sold_at": date.today().isoformat(),
            "due_date": (date.today() + timedelta(days=15)).isoformat(), "note": "自动验收",
        })
        order = self.submit("/api/v1/sales/orders", order)
        _, body = self.verifier.post(f"/api/v1/sales/orders/{order['id']}/approve", {"expected_version": order["version"]})
        self.check("销售单换人审批通过", self.record_of(body)["status"] == "approved")

        delivery = self.create("/api/v1/sales/deliveries", {
            "code": f"{PREFIX}-DLV-01", "name": "首批草鱼交付", "sales_order_id": order["id"],
            "harvest_document_id": self.ids["harvest"], "quantity": 450,
            "delivered_at": datetime.now().replace(microsecond=0).isoformat(),
            "transport_info": "浙A·2T 冷链车", "acceptance_note": "验收合格",
        })
        self.ids["delivery"] = int(delivery["id"])
        self.check("交付带凭据核验通过", self.advance("/api/v1/sales/deliveries", delivery, evidence=True)["status"] == "verified")

        receivable = self._receivable_of_delivery()
        self.check("交付核验后自动生成应收", bool(receivable))
        if not receivable:
            return
        self.ids["receivable"] = int(receivable["id"])
        amount = float(receivable.get("balance") or receivable.get("amount") or 7560)
        receipt = self.create("/api/v1/sales/receipts", {
            "code": f"{PREFIX}-RCP-01", "name": "首批草鱼货款（全额）", "receivable_id": self.ids["receivable"],
            "amount": amount, "received_at": date.today().isoformat(), "receipt_method": "bank_transfer", "note": "自动验收",
        })
        self.check("收款带凭据核验通过", self.advance("/api/v1/sales/receipts", receipt, evidence=True)["status"] == "verified")
        updated = self._receivable_of_delivery()
        self.check(
            "应收余额按收款核销为 0",
            bool(updated) and float(updated.get("balance") or 0) == 0.0,
            f"余额 {updated.get('balance') if updated else '—'}",
        )

    def _receivable_of_delivery(self) -> dict | None:
        _, body = self.writer.get("/api/v1/sales/receivables?page=1&page_size=100")
        for row in body["data"]["items"]:
            link = int(row.get("source_delivery_id") or row.get("sales_delivery_id") or 0)
            if link == self.ids["delivery"]:
                self.ids["receivable"] = int(row["id"])
                return row
        return None
