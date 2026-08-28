from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date

from backend.layers.common.governance.lifecycle import DomainError


@dataclass(frozen=True)
class Field:
    key: str
    label: str
    required: bool = False
    kind: str = "text"
    example: str = ""
    allowed: tuple[str, ...] = ()


@dataclass(frozen=True)
class Template:
    code: str
    name: str
    group: str
    version: str
    fields: tuple[Field, ...]
    importable: bool = False

    def public(self) -> dict[str, object]:
        return {**asdict(self), "fields": [asdict(field) for field in self.fields], "updated_at": date.today().isoformat()}


CODE = Field("code", "业务编号", True, example="CODE-001")
NAME = Field("name", "名称", True, example="示例名称")
DATE = Field("happened_at", "发生日期", True, "date", "2026-08-17")
QTY = Field("quantity", "数量", True, "positive", "100")
AMOUNT = Field("amount", "金额", True, "positive", "1280.00")


def _template(code: str, name: str, group: str, *fields: Field, importable: bool = True) -> Template:
    """除 inventory-ledger（系统只追加账本）外，其余模板全部开放导入。"""
    return Template(code, name, group, "1.0", fields or (CODE, NAME), importable)


WAREHOUSE_ID = Field("warehouse_id", "仓库ID", True, "integer", "1")
TEMPLATES = (
    _template("ponds", "塘口档案", "基础档案", CODE, NAME, Field("farm_id", "基地ID", True, "integer", "1"), Field("area_id", "区域ID", True, "integer", "1"), Field("capacity_mu", "面积（亩）", True, "positive", "12.5"), Field("species", "品种", True, example="草鱼")),
    _template("batches", "养殖批次", "塘口与批次", CODE, Field("species", "品种", True), Field("pond_id", "当前塘口ID", True, "integer"), DATE, QTY),
    _template("stocking", "投苗记录", "塘口与批次", CODE, Field("batch_id", "批次ID", True, "integer"), QTY, DATE),
    _template("samplings", "规格抽样", "塘口与批次", CODE, Field("batch_id", "批次ID", True, "integer"), QTY, DATE),
    _template("losses", "损耗记录", "塘口与批次", CODE, Field("batch_id", "批次ID", True, "integer"), QTY, DATE, Field("reason", "原因", True)),
    _template("transfers", "转塘记录", "塘口与批次", CODE, Field("batch_id", "批次ID", True, "integer"), Field("target_pond_id", "目标塘口ID", True, "integer"), QTY, DATE),
    _template("feed-plans", "喂养计划", "日常养殖", CODE, NAME, Field("pond_id", "塘口ID", True, "integer"), Field("batch_id", "批次ID", True, "integer"), Field("material_id", "饲料ID", True, "integer"), QTY, Field("planned_at", "计划时间", True, "datetime", "2026-08-26 08:00")),
    _template("feed-logs", "喂养记录", "日常养殖", CODE, Field("pond_id", "塘口ID", True, "integer"), Field("batch_id", "批次ID", True, "integer"), Field("material_id", "饲料ID", True, "integer"), Field("feed_task_id", "投喂任务ID", True, "integer"), Field("material_issue_request_id", "领料申请ID", True, "integer"), QTY, DATE),
    _template("feed-tasks", "派工任务", "日常养殖", CODE, NAME, Field("assignee_id", "作业员ID", True, "integer"), Field("pond_id", "塘口ID", True, "integer"), DATE),
    _template("daily-operations", "日常作业", "日常养殖", CODE, NAME, Field("pond_id", "塘口ID", True, "integer"), DATE),
    _template("materials", "物料档案", "主数据", CODE, NAME, Field("category", "分类", True), Field("specification", "规格"), Field("unit", "单位", True), Field("safety_stock", "安全库存", False, "number", "100")),
    _template("receipts", "入库记录", "物料与仓储", CODE, NAME, WAREHOUSE_ID, Field("material_id", "物料ID", True, "integer"), Field("lot_no", "物料批次", True), QTY, DATE),
    _template("issues", "出库记录", "物料与仓储", CODE, NAME, WAREHOUSE_ID, Field("material_id", "物料ID", True, "integer"), Field("inventory_lot_id", "库存批次ID", True, "integer"), Field("source_document_id", "领用申请ID", True, "integer"), QTY, DATE),
    _template("warehouse-transfers", "调拨记录", "物料与仓储", CODE, NAME, WAREHOUSE_ID, Field("target_warehouse_id", "目标仓库ID", True, "integer", "2"), Field("material_id", "物料ID", True, "integer"), QTY, DATE),
    _template("returns", "退库记录", "物料与仓储", CODE, NAME, WAREHOUSE_ID, Field("material_id", "物料ID", True, "integer"), Field("inventory_lot_id", "库存批次ID", True, "integer"), Field("source_document_id", "原出库单ID", True, "integer"), QTY, DATE),
    _template("stocktakes", "盘点记录", "物料与仓储", CODE, NAME, WAREHOUSE_ID, Field("material_id", "物料ID", True, "integer"), Field("inventory_lot_id", "库存批次ID", True, "integer"), QTY, DATE),
    _template("scraps", "报损报废记录", "物料与仓储", CODE, NAME, WAREHOUSE_ID, Field("material_id", "物料ID", True, "integer"), Field("inventory_lot_id", "库存批次ID", True, "integer"), QTY, DATE, Field("reason", "原因", True)),
    _template("suppliers", "供应商", "采购与付款", CODE, NAME, Field("contact_name", "联系人"), Field("phone", "电话")),
    _template("purchase-orders", "采购明细", "采购与付款", CODE, NAME, Field("supplier_id", "供应商ID", True, "integer"), Field("material_id", "物料ID", True, "integer"), WAREHOUSE_ID, QTY, Field("unit_price", "单价", True, "positive"), Field("due_date", "付款到期日", True, "date", "2026-09-16")),
    _template("payments", "付款记录", "采购与付款", CODE, Field("payable_id", "应付ID", True, "integer"), AMOUNT, DATE, Field("payment_method", "付款方式", True, "", "bank_transfer", allowed=("bank_transfer", "cash", "check", "digital_wallet", "other"))),
    _template("customers", "客户", "销售与收款", CODE, NAME, Field("contact_name", "联系人"), Field("phone", "电话")),
    _template("sales-orders", "销售明细", "销售与收款", CODE, Field("customer_id", "客户ID", True, "integer"), Field("batch_id", "批次ID", True, "integer"), QTY, Field("unit_price", "单价", True, "positive"), Field("unit", "单位", False, "", "kg", allowed=("kg", "jin", "tail")), Field("sold_at", "销售日期", False, "date", "2026-08-17"), Field("due_date", "收款到期日", False, "date", "2026-09-16")),
    _template("harvests", "出塘记录", "销售与收款", CODE, Field("batch_id", "批次ID", True, "integer"), QTY, DATE),
    _template("customer-receipts", "收款记录", "销售与收款", CODE, Field("receivable_id", "应收ID", True, "integer"), AMOUNT, DATE, Field("receipt_method", "收款方式", False, "", "bank_transfer", allowed=("bank_transfer", "cash", "check", "digital_wallet", "other"))),
    _template("expenses", "费用登记", "成本与经营", CODE, NAME, Field("farm_id", "基地ID", True, "integer"), Field("category_code", "费用类别", True), AMOUNT, DATE),
    _template("assets", "设备资产", "成本与经营", CODE, NAME, Field("farm_id", "基地ID", True, "integer"), Field("asset_type", "资产类别", True, "", "equipment", allowed=("equipment", "infrastructure", "lease")), Field("category_code", "成本分类", True), AMOUNT, Field("salvage_value", "预计残值", True, "number", "0"), Field("useful_life_months", "使用寿命（月）", True, "integer", "60"), Field("purchase_date", "购买日期", True, "date", "2026-08-17"), Field("depreciation_start_date", "折旧开始日", True, "date", "2026-08-17")),
    _template("leases", "租赁合同", "成本与经营", CODE, NAME, Field("farm_id", "基地ID", True, "integer", "1"), Field("category_code", "成本分类", False), AMOUNT, DATE),
    _template("cost-adjustments", "成本调整", "成本与经营", CODE, Field("source_id", "原成本ID", True, "integer"), AMOUNT, Field("reason", "调整原因", True)),
    _template("business-settings", "基础参数", "系统管理", CODE, NAME, Field("group_code", "参数分组", True), Field("value_text", "参数值", True)),
    _template("inventory-ledger", "库存流水", "物料与仓储", CODE, Field("material_id", "物料ID", True, "integer"), Field("business_type", "业务类型", True), QTY, DATE, importable=False),
)


def all_templates() -> list[dict[str, object]]:
    return [item.public() for item in TEMPLATES]


def get_template(code: str) -> Template:
    template = next((item for item in TEMPLATES if item.code == code), None)
    if template is None:
        raise DomainError("TEMPLATE_NOT_FOUND", "导入模板不存在", 404)
    return template
