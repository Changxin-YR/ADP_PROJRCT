"""阶段 7：成本与结算；阶段 13：请购闭环；阶段 14：退货闭环。"""
from __future__ import annotations

from datetime import date, timedelta

from .client import FARM_ID, ORGANIZATION_ID, PREFIX, ApiError

EXPENSES = (
    ("labor", 18000.00, f"{PREFIX}-EXP-01", "public", None, None),
    ("electricity", 6200.50, f"{PREFIX}-EXP-02", "public", None, None),
    ("other", 2500.00, f"{PREFIX}-EXP-03", "direct", "pond", "pond1"),
)


class FinanceFlows:
    def cost_and_settlement(self) -> None:
        self.section("阶段 7：费用 → 确认 → 分摊 → 结算 → 锁账")
        period_start, period_end = date.today().replace(day=1).isoformat(), date.today().isoformat()
        for category, amount, ref, nature, target_type, target_key in EXPENSES:
            payload = {
                "organization_id": ORGANIZATION_ID, "farm_id": FARM_ID, "area_id": self.ids.get("area", 1),
                "category_code": category, "amount": amount, "occurred_on": period_end,
                "period_start": period_start, "period_end": period_end, "cost_nature": nature,
                "source_type": "manual_expense", "source_ref": ref,
            }
            if target_type:
                payload["target_type"] = target_type
                payload["target_id"] = self.ids[target_key]
            row = self.create("/api/v1/cost/expenses", payload)
            self.ids[ref] = int(row["id"])
            row = self.advance("/api/v1/cost/expenses", self.submit("/api/v1/cost/expenses", row), evidence=True)
            if row.get("status") == "verified":
                row = self.confirm_cost("/api/v1/cost/expenses", row, "cost:expense")
            self.check(f"费用 {ref} 走完提交→核验→确认", row.get("status") == "confirmed", f"状态 {row.get('status')}")

        asset = self.create("/api/v1/cost/assets", {
            "code": f"{PREFIX}-AST-01", "name": "[验收]1.5kW 增氧机", "asset_type": "equipment",
            "category_code": "equipment", "purchase_date": (date.today() - timedelta(days=20)).isoformat(),
            "original_value": 4800.00, "salvage_value": 200.00, "useful_life_months": 60,
            "depreciation_start_date": (date.today() - timedelta(days=19)).isoformat(),
            "organization_id": ORGANIZATION_ID, "farm_id": FARM_ID, "area_id": self.ids.get("area", 1),
            "target_type": "pond", "target_id": self.ids["pond1"], "note": "自动验收",
        })
        asset = self.advance("/api/v1/cost/assets", asset, evidence=True)
        if asset.get("status") == "verified":
            asset = self.confirm_cost("/api/v1/cost/assets", asset, "cost:asset")
        self.check("资产走完提交→核验→确认", asset.get("status") == "confirmed", f"状态 {asset.get('status')}")

        _, body = self.verifier.post("/api/v1/cost/allocations", {
            "period_start": period_start, "period_end": period_end, "farm_id": FARM_ID, "area_id": self.ids.get("area"),
        })
        allocation = body["data"]
        self.ids["allocation"] = int(allocation["id"])
        self.check(
            "成本分摊来源合计 = 已分摊合计",
            float(allocation.get("source_total") or 0) == float(allocation.get("allocated_total") or 0),
            f"来源 {allocation.get('source_total')} / 分摊 {allocation.get('allocated_total')}",
        )

        settlement = self.create("/api/v1/cost/settlements", {
            "name": f"{PREFIX} 期间结算", "period_start": period_start, "period_end": period_end,
            "allocation_run_id": self.ids["allocation"],
        })
        settlement = self.verify("/api/v1/cost/settlements", self.submit("/api/v1/cost/settlements", settlement))
        _, body = self.verifier.post(f"/api/v1/cost/settlements/{settlement['id']}/confirm", {"expected_version": settlement["version"]})
        self.check("期间结算锁定", self.record_of(body).get("status") == "confirmed")

        # 新增闭环 A2：已确认结算的期间不得再补写成本
        self.expect_error(
            "反向：已确认结算期间禁止补写成本",
            lambda: self.create("/api/v1/cost/expenses", {
                "organization_id": ORGANIZATION_ID, "farm_id": FARM_ID, "area_id": self.ids.get("area", 1),
                "category_code": "other", "amount": 100, "occurred_on": period_end,
                "period_start": period_start, "period_end": period_end, "cost_nature": "public",
                "source_type": "manual_expense", "source_ref": f"{PREFIX}-EXP-LATE",
            }),
            status=409, code="COST_PERIOD_LOCKED",
        )
        _, body = self.writer.get(f"/api/v1/cost/reports/net?period_start={period_start}&period_end={period_end}")
        self.check("净额报表可查询", "data" in body)

    def requisition_loop(self) -> None:
        """阶段 13：库存预警 → 请购单 → 采购单（新增闭环 B）。"""
        self.section("阶段 13：库存预警 → 请购单 → 采购单（新增）")
        try:
            requisition = self.create("/api/v1/purchase/requisitions", {
                "code": f"{PREFIX}-REQ-01", "name": "补货请购：草鱼膨化饲料",
                "material_id": self.ids["material_FEED"], "quantity": 300,
                "warehouse_id": self.ids["warehouse"], "reason": "安全库存低于阈值，触发补货",
                "alert_key": f"low_stock:material:{self.ids['material_FEED']}",
            })
        except ApiError as error:
            self.step("请购单创建", "FAIL", f"{error.status} {error.code}")
            return
        self.ids["requisition"] = int(requisition["id"])
        requisition = self.submit("/api/v1/purchase/requisitions", requisition)
        self.check("请购单提交成功", requisition["status"] == "submitted", f"状态 {requisition['status']}")
        self.expect_error(
            "反向：请购经办人自己审批被拒绝",
            lambda: self.writer.post(
                f"/api/v1/purchase/requisitions/{requisition['id']}/approve", {"expected_version": requisition["version"]}
            ),
            status=403, code="SELF_APPROVAL_FORBIDDEN",
        )
        _, body = self.verifier.post(
            f"/api/v1/purchase/requisitions/{requisition['id']}/approve", {"expected_version": requisition["version"]}
        )
        requisition = self.record_of(body)
        self.check("请购单换人审批通过", requisition["status"] == "approved", f"状态 {requisition['status']}")

        convert = {
            "expected_version": requisition["version"], "supplier_id": self.ids["supplier"], "unit_price": 12.5,
            "due_date": (date.today() + timedelta(days=30)).isoformat(), "warehouse_id": self.ids["warehouse"],
        }
        _, body = self.writer.post(f"/api/v1/purchase/requisitions/{requisition['id']}/convert", convert)
        order = self.record_of(body)
        self.ids["requisition_order"] = int(order["id"])
        self.check("请购单转换为采购单草稿", order.get("status") == "draft", f"采购单 {order.get('code')}")
        self.check(
            "采购单回填请购来源",
            int(order.get("requisition_id") or 0) == int(requisition["id"]),
            f"requisition_id={order.get('requisition_id')}",
        )
        self.expect_error(
            "反向：同一请购单重复转换被拒绝",
            lambda: self.writer.post(f"/api/v1/purchase/requisitions/{requisition['id']}/convert", convert),
            status=409, code="PURCHASE_REQUISITION_ALREADY_CONVERTED",
        )

    def returns_loop(self) -> None:
        """阶段 14：退货闭环（冲减应付/应收 + 退回库存，新增闭环 C）。"""
        self.section("阶段 14：退货闭环（新增）")
        if not self.ids.get("receipt") or not self.ids.get("delivery") or not self.ids.get("inventory_lot"):
            self.step("退货闭环", "FAIL", "缺少入库单/交付单/物料批次 ID，阶段 5/6 未跑通")
            return

        try:
            # amount 由后端按 数量 × 来源单价 计算，不进请求体（见 return_store.create_return）
            purchase_return = self.create("/api/v1/purchase/returns", {
                "code": f"{PREFIX}-PRET-01", "name": "饲料外包装破损退回",
                "source_receipt_id": self.ids["receipt"], "warehouse_id": self.ids["warehouse"],
                "material_id": self.ids["material_FEED"], "inventory_lot_id": self.ids["inventory_lot"],
                "quantity": 20, "reason": "外包装破损，退回供应商",
            })
        except ApiError as error:
            self.step("供应商退货创建", "FAIL", f"{error.status} {error.code} {error.message}")
        else:
            self.ids["purchase_return"] = int(purchase_return["id"])
            purchase_return = self.advance("/api/v1/purchase/returns", purchase_return)
            self.check("供应商退货核验通过（冲减应付）", purchase_return["status"] == "verified", f"状态 {purchase_return['status']}")

        try:
            sales_return = self.create("/api/v1/sales/returns", {
                "code": f"{PREFIX}-SRET-01", "name": "客户退回部分草鱼",
                "source_delivery_id": self.ids["delivery"], "receivable_id": self.ids["receivable"],
                "quantity": 20, "refund_amount": 300, "reason": "客户验收后短少，按实退补",
            })
        except ApiError as error:
            self.step("客户退货创建", "FAIL", f"{error.status} {error.code} {error.message}")
            return
        self.ids["sales_return"] = int(sales_return["id"])
        sales_return = self.advance("/api/v1/sales/returns", sales_return)
        self.check("客户退货核验通过（冲减应收）", sales_return["status"] == "verified", f"状态 {sales_return['status']}")
