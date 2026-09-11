"""智能体对外话术词典：路径动作、资源名、字段名 → 业务人员看得懂的中文。

只放数据表，不放逻辑；``agent_humanize`` 负责组合这些表生成人话。
"""

from __future__ import annotations

# 精确路径 → 动作中文名（比按动词猜更准，优先命中）
PATH_ACTIONS: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/master-data/ponds/{pond_id}/status-changes"): "申请塘口状态变更",
    ("POST", "/api/v1/master-data/ponds/{pond_id}/status-changes/{request_id}/verify"): "核验塘口状态变更",
    ("POST", "/api/v1/production/batches/{batch_id}/status"): "变更批次状态",
    ("POST", "/api/v1/data-exchange/imports/preview"): "预检导入文件",
    ("POST", "/api/v1/data-exchange/imports/{batch_id}/confirm"): "确认导入",
    ("POST", "/api/v1/data-exchange/imports/{batch_id}/revoke"): "撤销导入",
    ("POST", "/api/v1/data-exchange/exports"): "导出数据",
    ("POST", "/api/v1/cost/allocations"): "执行成本分摊",
    ("PUT", "/api/v1/cost/allocation-rules"): "保存分摊规则",
    ("POST", "/api/v1/cost/assets/{record_id}/depreciate"): "计提折旧",
    ("POST", "/api/v1/cost/assets/{record_id}/confirm"): "确认资产",
    ("POST", "/api/v1/cost/assets/{record_id}/submit"): "提交资产",
    ("POST", "/api/v1/cost/assets/{record_id}/verify"): "核验资产",
    ("POST", "/api/v1/cost/entries/{entry_id}/confirm"): "确认成本分录",
    ("POST", "/api/v1/cost/entries/{entry_id}/reverse"): "冲销成本分录",
    ("POST", "/api/v1/cost/entries/{entry_id}/submit"): "提交成本分录",
    ("POST", "/api/v1/cost/entries/{entry_id}/verify"): "核验成本分录",
    ("POST", "/api/v1/cost/expenses/{record_id}/confirm"): "确认费用",
    ("POST", "/api/v1/cost/expenses/{record_id}/reverse"): "冲销费用",
    ("POST", "/api/v1/cost/expenses/{record_id}/submit"): "提交费用",
    ("POST", "/api/v1/cost/expenses/{record_id}/verify"): "核验费用",
    ("POST", "/api/v1/cost/settlements/{record_id}/confirm"): "确认期间结算",
    ("POST", "/api/v1/cost/settlements/{record_id}/reverse"): "冲销期间结算",
    ("POST", "/api/v1/cost/settlements/{record_id}/submit"): "提交期间结算",
    ("POST", "/api/v1/cost/settlements/{record_id}/verify"): "核验期间结算",
    ("POST", "/api/v1/purchase/orders/{record_id}/submit"): "提交采购单",
    ("POST", "/api/v1/purchase/orders/{record_id}/verify"): "核验采购单",
    ("POST", "/api/v1/purchase/orders/{record_id}/approve"): "审批采购单",
    ("POST", "/api/v1/purchase/orders/{record_id}/reject"): "驳回采购单",
    ("POST", "/api/v1/purchase/orders/{record_id}/dispatch"): "发出采购单",
    ("POST", "/api/v1/purchase/orders/{record_id}/receive"): "采购收货",
    ("POST", "/api/v1/purchase/orders/{record_id}/cancel"): "取消采购单",
    ("POST", "/api/v1/purchase/payments"): "登记付款",
    ("POST", "/api/v1/sales/orders/{record_id}/submit"): "提交销售单",
    ("POST", "/api/v1/sales/orders/{record_id}/verify"): "核验销售单",
    ("POST", "/api/v1/sales/orders/{record_id}/dispatch"): "发出销售单",
    ("POST", "/api/v1/sales/orders/{record_id}/deliver"): "销售发货",
    ("POST", "/api/v1/sales/orders/{record_id}/cancel"): "取消销售单",
    ("POST", "/api/v1/sales/receipts"): "登记收款",
    ("POST", "/api/v1/admin/applications/{application_id}/approve"): "通过注册申请",
    ("POST", "/api/v1/admin/applications/{application_id}/reject"): "驳回注册申请",
    ("POST", "/api/v1/admin/users"): "新增账号",
    ("POST", "/api/v1/admin/users/{user_id}/retire"): "停用账号",
    ("POST", "/api/v1/admin/users/{user_id}/reset-password"): "重置密码",
    ("POST", "/api/v1/admin/users/{user_id}/password-reset"): "重置密码",
    ("POST", "/api/v1/admin/roles/{role_id}/copies"): "复制角色",
    ("PUT", "/api/v1/admin/roles/{role_id}/permissions"): "调整角色权限",
    ("PUT", "/api/v1/admin/users/{user_id}/grants"): "调整账号授权",
    ("PATCH", "/api/v1/admin/users/{user_id}/status"): "调整账号状态",
}

# 路径尾段 → 动作前缀（例如 .../submit → 提交某某）
PATH_TAILS: dict[str, str] = {
    "submit": "提交",
    "verify": "核验",
    "confirm": "确认",
    "revoke": "撤销",
    "archive": "归档",
    "approve": "审批",
    "reject": "驳回",
    "dispatch": "发出",
    "receive": "接收",
    "cancel": "取消",
}

VERB_ACTIONS: dict[str, str] = {"POST": "新增", "PUT": "保存", "PATCH": "修改", "DELETE": "删除"}

# 业务域 → resource 段 → 中文名
DOMAIN_RESOURCES: dict[str, dict[str, str]] = {
    "production": {
        "samplings": "抽样记录", "transfers": "转塘记录", "losses": "损耗记录", "harvests": "出塘记录",
        "feed-plans": "投喂计划", "feed-tasks": "投喂任务", "feed-logs": "投喂记录",
        "daily-operations": "日常巡塘", "batches": "养殖批次", "medications": "用药记录",
        "feeding": "投喂记录", "feedings": "投喂记录",
    },
    "master-data": {
        "ponds": "塘口档案", "areas": "片区档案", "pond-groups": "塘口分组", "farms": "养殖场档案",
        "materials": "物料档案", "partners": "业务伙伴", "customers": "客户档案",
        "suppliers": "供应商档案", "species": "养殖品种",
    },
    "warehouse": {
        "issues": "出库单", "receipts": "入库单", "transfers": "调拨单", "stocktakes": "盘点单",
        "scraps": "报废单", "alerts": "库存预警", "ledgers": "库存台账",
    },
    "cost": {
        "entries": "成本分录", "expenses": "费用单", "assets": "资产卡片", "settlements": "期间结算",
        "allocations": "成本分摊", "reports": "成本报表",
    },
    "purchase": {"orders": "采购单", "payments": "付款记录", "returns": "供应商退货"},
    "sales": {"orders": "销售单", "receipts": "收款记录", "returns": "客户退货"},
    "workbench": {"work-items": "待办事项", "notifications": "通知", "summary": "工作台摘要"},
    "data-exchange": {"imports": "导入批次", "templates": "导入模板", "attachments": "附件", "exports": "导出任务"},
    "admin": {"users": "系统账号", "roles": "角色", "applications": "注册申请", "audit-logs": "操作日志", "options": "基础选项"},
}

RESOURCE_LABELS: dict[str, str] = {}
for _bucket in DOMAIN_RESOURCES.values():
    RESOURCE_LABELS.update(_bucket)

# 参数字段 → 中文标签
FIELD_LABELS: dict[str, str] = {
    "resource": "对象类型", "resource_type": "对象类型", "pond_id": "塘口编号", "pond_code": "塘口编码", "pond_name": "塘口名称",
    "area_id": "片区编号", "area_name": "片区名称", "pond_group_id": "塘口分组编号", "farm_id": "养殖场编号",
    "batch_id": "批次编号", "batch_code": "批次编号", "batch_status": "批次状态", "code": "编码", "name": "名称",
    "species": "养殖品种", "current_spec": "当前规格", "stocking_spec": "投苗规格", "quantity": "数量",
    "weight_kg": "重量（kg）", "avg_weight_kg": "平均体重（kg）", "unit_price": "单价", "amount": "金额",
    "total_amount": "合计金额", "quantity_delta": "数量变动", "weight_delta_kg": "重量变动（kg）",
    "material_id": "物料编号", "material_name": "物料名称", "partner_id": "业务伙伴编号", "supplier_id": "供应商",
    "customer_id": "客户编号", "operator_id": "经办人", "manager_id": "负责人", "manager_name": "负责人",
    "happened_at": "发生时间", "occurred_at": "发生时间", "expected_at": "预计时间", "due_date": "到期日",
    "started_at": "开始时间", "finished_at": "完成时间", "created_at": "创建时间", "updated_at": "更新时间",
    "verified_at": "核验时间", "status": "状态", "status_text": "状态", "note": "说明", "notes": "备注",
    "reason": "原因", "remark": "备注", "location": "位置", "location_text": "位置", "capacity_mu": "养殖面积（亩）",
    "water_source": "水源", "aerator_count": "增氧机数量", "loss_reason": "损耗原因",
    "attachment_id": "附件", "template_code": "模板", "record_id": "记录", "entry_id": "分录",
    "expense_id": "费用单", "settlement_id": "结算单", "asset_id": "资产卡片", "order_id": "单据",
    "payment_amount": "付款金额", "received_amount": "收款金额", "tax_rate": "税率", "department": "部门",
    "role_ids": "角色", "permissions": "权限", "user_id": "账号", "application_id": "注册申请", "role_id": "角色",
    "scope_type": "范围类型", "scope_id": "范围对象", "method": "方式", "category": "分类", "type": "类型",
    "source": "来源", "target": "目标", "page": "页码", "page_size": "每页条数", "keyword": "关键词",
    "search": "搜索词", "uninspected_on": "未巡检日期", "pond_ids": "塘口范围", "id": "编号",
}

# 风险提示：确认卡片只在回退模式下出现
RISK_NORMAL = "这会改动业务数据"
RISK_ADMIN = "这会改动账号、角色或权限，请先核对再执行"
