"""断言框架 + 通用单据流转：各业务域的阶段实现通过混入本类复用这些能力。"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta

from .client import ORGANIZATION_ID, PREFIX, ApiError, Client

PASS, FAIL = "PASS", "FAIL"
FARM_ID = 1
RECORD_KEYS = ("record", "warehouse", "entry", "asset", "settlement", "status_change")


class Runner:
    """阶段实现的公共基类：负责断言、记录 ID、以及草稿→提交→换人核验的通用流转。"""

    def __init__(self, writer: Client, verifier: Client, *, only: str | None = None) -> None:
        self.writer, self.verifier = writer, verifier
        self.results: list[tuple[str, str, str]] = []
        self.ids: dict[str, int] = {}
        self.only = only

    # ---------- 断言 ----------
    def step(self, name: str, status: str, detail: str = "") -> None:
        self.results.append((name, status, detail))
        print(f"  {'✓' if status == PASS else '✗'} {name}" + (f"  | {detail}" if detail else ""))

    def check(self, name: str, condition: bool, detail: str = "") -> bool:
        self.step(name, PASS if condition else FAIL, detail)
        return bool(condition)

    def expect_error(self, name: str, fn, *, status: int, code: str | None = None) -> None:
        try:
            fn()
        except ApiError as error:
            ok = error.status == status and (code is None or error.code == code)
            self.step(name, PASS if ok else FAIL, f"实际 {error.status} {error.code}")
            return
        except Exception as error:  # noqa: BLE001
            self.step(name, FAIL, f"非预期异常：{error}")
            return
        self.step(name, FAIL, "预期报错但成功了")

    def section(self, title: str) -> None:
        print(f"\n{title}")

    # ---------- 响应解包（各模块包裹键不一致） ----------
    @classmethod
    def record_of(cls, body: dict) -> dict:
        data = body.get("data")
        if not isinstance(data, dict):
            raise ApiError(500, "UNEXPECTED_RESPONSE", f"响应结构异常：{json.dumps(body, ensure_ascii=False, default=str)[:200]}")
        for key in RECORD_KEYS:
            candidate = data.get(key)
            if isinstance(candidate, dict) and "id" in candidate:
                return candidate
        if "id" in data:
            return data
        for value in data.values():
            if isinstance(value, dict) and "id" in value:
                return value
        raise ApiError(500, "UNEXPECTED_RESPONSE", f"响应中没有记录对象：{json.dumps(data, ensure_ascii=False, default=str)[:200]}")

    # ---------- 单据流转 ----------
    def create(self, base: str, payload: dict) -> dict:
        _, body = self.writer.post(base, payload)
        return self.record_of(body)

    def submit(self, base: str, record: dict) -> dict:
        _, body = self.writer.post(f"{base}/{record['id']}/submit", {"expected_version": record["version"]})
        return self.record_of(body)

    def verify(self, base: str, record: dict, *, evidence: list[int] | None = None, actor: Client | None = None) -> dict:
        payload: dict = {"expected_version": record["version"]}
        if evidence:
            payload["evidence_attachment_ids"] = evidence
        _, body = (actor or self.verifier).post(f"{base}/{record['id']}/verify", payload)
        return self.record_of(body)

    def advance(self, base: str, record: dict, *, evidence: bool = False) -> dict:
        """草稿 → 提交 → 换人核验；需要凭据时自动上传后再核验。"""
        current = record
        if current.get("status") == "draft":
            current = self.submit(base, current)
        if current.get("status") != "submitted":
            return current
        attachment_id = self.verifier.upload_attachment("manual_test:evidence", current["id"]) if evidence else None
        try:
            return self.verify(base, current, evidence=[attachment_id] if attachment_id else None)
        except ApiError as error:
            if error.code == "EVIDENCE_REQUIRED" and not attachment_id:
                attachment_id = self.verifier.upload_attachment("manual_test:evidence", current["id"])
                return self.verify(base, current, evidence=[attachment_id])
            raise

    def confirm_cost(self, base: str, record: dict, entity_type: str) -> dict:
        attachment = self.verifier.upload_attachment(entity_type, record["id"])
        _, body = self.verifier.post(
            f"{base}/{record['id']}/confirm",
            {"expected_version": record["version"], "evidence_attachment_ids": [attachment]},
        )
        return self.record_of(body)

    # ---------- 阶段 0：联通 ----------
    def connectivity(self) -> None:
        self.section("阶段 0：前后端联通与鉴权")
        writer, verifier = self.writer.login(), self.verifier.login()
        self.check("写入账号登录成功", bool(writer.get("id")), f"{writer.get('name')} / {writer.get('status')}")
        self.check("核验账号登录成功", bool(verifier.get("id")), f"{verifier.get('name')} / {verifier.get('status')}")
        self.check("两个账号不是同一人（否则自审会被拒绝）", writer.get("id") != verifier.get("id"))
        _, body = self.writer.get("/api/v1/workbench/summary")
        self.check("工作台汇总接口可用", "data" in body)
        _, body = self.writer.get("/api/v1/master-data/areas?page=1&page_size=100")
        verified = [row for row in body["data"]["items"] if row.get("status") == "verified"]
        self.check("存在已核验区域（后续塘口依赖它）", bool(verified), f"{len(verified)} 个")
        if verified:
            self.ids["area"] = int(verified[0]["id"])

    # ---------- 阶段 1-2：主数据 ----------
    def master_data(self) -> None:
        self.section("阶段 1-2：主数据（分组 / 塘口 / 供应商 / 物料 / 客户）")
        area_id, master = self.ids.get("area") or 1, "/api/v1/master-data"

        group = self.create(f"{master}/pond-groups", {
            "organization_id": ORGANIZATION_ID, "farm_id": FARM_ID, "area_id": area_id,
            "code": f"{PREFIX}-GRP-01", "name": "[验收]北区成鱼塘组", "description": "自动验收创建",
        })
        self.ids["group"] = int(group["id"])
        self.check("塘口分组 草稿→提交→换人核验", self.advance(f"{master}/pond-groups", group)["status"] == "verified")

        for index in (1, 2):
            pond = self.create(f"{master}/ponds", {
                "organization_id": ORGANIZATION_ID, "farm_id": FARM_ID, "area_id": area_id,
                "pond_group_id": self.ids["group"], "code": f"{PREFIX}-POND-{index:02d}",
                "name": f"[验收]北区{index}号塘", "species": "草鱼", "capacity_mu": 40 + index,
                "location_text": f"北区{index}号", "aerator_count": index + 1,
                "stocking_spec": "100 尾/斤", "current_spec": "待投苗", "stock_quantity": 0,
                "stock_quantity_source": "manual", "pond_status": "build",
            })
            self.ids[f"pond{index}"] = int(pond["id"])
            self.check(f"塘口{index}号 核验通过", self.advance(f"{master}/ponds", pond)["status"] == "verified")
        self.expect_error(
            "反向：新建塘口直接进入养殖中被拒绝",
            lambda: self.create(f"{master}/ponds", {
                "code": f"{PREFIX}-POND-BAD", "name": "非法状态塘口", "area_id": area_id, "pond_status": "farming",
            }),
            status=400, code="POND_STATUS_INVALID",
        )

        supplier = self.create(f"{master}/suppliers", {
            "organization_id": ORGANIZATION_ID, "farm_id": FARM_ID, "area_id": area_id,
            "code": f"{PREFIX}-SUP-01", "name": "[验收]湖州水产物资有限公司",
            "contact_name": "王建国", "phone": "0572-2388666", "settlement_days": 30, "credit_limit": 200000,
        })
        self.ids["supplier"] = int(supplier["id"])
        self.check("供应商核验通过", self.advance(f"{master}/suppliers", supplier)["status"] == "verified")

        materials = {
            "FEED": ("[验收]草鱼膨化饲料", "饲料", "40kg/袋", "kg", 500, 180),
            "SEED": ("[验收]草鱼苗种", "苗种", "100尾/斤", "尾", 0, 0),
            "HEALTH": ("[验收]聚维酮碘", "动保", "500ml/瓶", "瓶", 10, 540),
        }
        for code, (name, category, spec, unit, safety, shelf) in materials.items():
            row = self.create(f"{master}/materials", {
                "organization_id": ORGANIZATION_ID, "farm_id": FARM_ID, "area_id": area_id,
                "code": f"{PREFIX}-MAT-{code}", "name": name, "category": category,
                "specification": spec, "unit": unit, "safety_stock": safety, "shelf_life_days": shelf,
                "default_supplier_id": self.ids["supplier"],
            })
            self.ids[f"material_{code}"] = int(row["id"])
            self.check(f"物料 {name} 核验通过", self.advance(f"{master}/materials", row)["status"] == "verified")

        customer = self.create(f"{master}/customers", {
            "organization_id": ORGANIZATION_ID, "farm_id": FARM_ID, "area_id": area_id,
            "code": f"{PREFIX}-CUS-01", "name": "[验收]杭州鲜活水产批发",
            "contact_name": "李美娟", "phone": "0571-88661234", "settlement_days": 15, "credit_limit": 150000,
        })
        self.ids["customer"] = int(customer["id"])
        self.check("客户核验通过", self.advance(f"{master}/customers", customer)["status"] == "verified")

    # ---------- 阶段 2C-3：仓库与批次 ----------
    def warehouse_and_batch(self) -> None:
        self.section("阶段 2C-3：仓库档案 + 养殖批次 + 存塘量汇总")
        _, body = self.writer.post("/api/v1/warehouse/warehouses", {
            "organization_id": ORGANIZATION_ID, "farm_id": FARM_ID, "area_id": self.ids.get("area", 1),
            "code": f"{PREFIX}-WH-01", "name": "[验收]综合一号仓", "location": "场区北门内", "status": "active",
        })
        self.ids["warehouse"] = int(self.record_of(body)["id"])
        self.check("仓库创建成功", bool(self.ids["warehouse"]), f"id={self.ids['warehouse']}")

        batch = self.create("/api/v1/production/batches", {
            "organization_id": ORGANIZATION_ID, "farm_id": FARM_ID, "area_id": self.ids.get("area", 1),
            "code": f"{PREFIX}-BATCH-01", "name": "[验收]草鱼 2026 秋批次", "pond_id": self.ids["pond1"],
            "species": "草鱼", "initial_quantity": 20000, "initial_weight_kg": 1600,
            "stocked_at": datetime.now().replace(microsecond=0).isoformat(),
            "expected_harvest_date": (date.today() + timedelta(days=90)).isoformat(),
            "batch_status": "stocked", "note": "自动验收创建",
        })
        self.ids["batch"] = int(batch["id"])
        self.check("批次核验通过", self.advance("/api/v1/production/batches", batch)["status"] == "verified")
        _, body = self.writer.get(f"/api/v1/production/batches/{self.ids['batch']}")
        record = body["data"]["record"]
        self.check("核验后批次存量入账", float(record.get("current_quantity") or 0) == 20000, f"当前存量 {record.get('current_quantity')}")
        _, body = self.writer.get(f"/api/v1/production/batches/{self.ids['batch']}/reconciliation")
        self.check("批次对账接口可用", "difference" in body["data"], json.dumps(body["data"], ensure_ascii=False))
        self.expect_error(
            "反向：批次初始数量与重量都为 0 被拒绝",
            lambda: self.create("/api/v1/production/batches", {
                "code": f"{PREFIX}-BATCH-BAD", "name": "非法批次", "pond_id": self.ids["pond1"],
                "species": "草鱼", "initial_quantity": 0, "initial_weight_kg": 0, "batch_status": "stocked",
            }),
            status=400, code="PRODUCTION_QUANTITY_REQUIRED",
        )
        self.pond_stock_summary()

    def pond_stock_summary(self) -> None:
        """塘口存塘量汇总（新增闭环 D）：只读汇总必须来自批次流水。"""
        try:
            _, body = self.writer.get(f"/api/v1/production/ponds/{self.ids['pond1']}/stock-summary")
            summary = body["data"]
            self.check(
                "塘口存塘量汇总来自批次流水",
                str(summary.get("data_source")) == "batch_ledger",
                f"来源 {summary.get('data_source')} / 合计 {summary.get('batch_stock')}",
            )
        except ApiError as error:
            self.step("塘口存塘量汇总来自批次流水", FAIL, f"{error.status} {error.code}（接口可能尚未实现）")

    # ---------- 阶段 16：安全边界 ----------
    def security(self) -> None:
        self.section("阶段 16：安全与一致性边界")
        _, body = self.writer.get(f"/api/v1/master-data/ponds/{self.ids['pond1']}")
        pond = body["data"]["record"]
        self.expect_error(
            "反向：已核验主数据编辑被拒绝（只读）",
            lambda: self.writer.patch(f"/api/v1/master-data/ponds/{pond['id']}", {"name": "改名", "expected_version": pond["version"]}),
            status=409, code="RECORD_READ_ONLY",
        )
        self.expect_error(
            "反向：请求体携带保留字段被拒绝",
            lambda: self.create("/api/v1/master-data/ponds", {
                "code": f"{PREFIX}-POND-X", "name": "非法字段", "area_id": self.ids.get("area", 1), "status": "verified",
            }),
            status=400, code="MASTER_FIELD_INVALID",
        )
        _, body = self.writer.get("/api/v1/work-items?page=1&page_size=50")
        data = body.get("data", {})
        items = data.get("items", []) if isinstance(data, dict) else []
        self.check("待办列表可读", isinstance(items, list), f"{len(items)} 条")

    # ---------- 编排 ----------
    PHASES = (
        ("阶段 0", "connectivity"),
        ("阶段 1", "master_data"),
        ("阶段 2", "warehouse_and_batch"),
        ("阶段 4", "daily_farming"),
        ("阶段 5", "purchase_and_payable"),
        ("阶段 6", "sales_and_receivable"),
        ("阶段 7", "cost_and_settlement"),
        ("阶段 13", "requisition_loop"),
        ("阶段 14", "returns_loop"),
        ("阶段 15", "batch_lifecycle"),
        ("阶段 16", "security"),
    )

    def run(self) -> int:
        started = time.time()
        for name, method in self.PHASES:
            if self.only and self.only not in name:
                continue
            try:
                getattr(self, method)()
            except ApiError as error:
                self.step(f"{name} 执行中断", FAIL, f"{error.status} {error.code} {error.message}")

        total, passed = len(self.results), sum(1 for _, status, _ in self.results if status == PASS)
        failed = [name for name, status, _ in self.results if status == FAIL]
        print("\n" + "=" * 64)
        print(f"汇总：{passed}/{total} 通过，用时 {time.time() - started:.1f}s")
        if failed:
            print(f"失败项（{len(failed)}）：")
            for name in failed:
                print(f"  ✗ {name}")
        print("=" * 64)
        print("本次创建的资源 ID：")
        for key, value in self.ids.items():
            print(f"  {key:<18} = {value}")
        print(f"数据前缀：{PREFIX}")
        return 0 if not failed else 1
