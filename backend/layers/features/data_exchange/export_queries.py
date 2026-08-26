"""导出资源定义：resource -> SQL（{scope} 占位由 store 按用户数据范围填充）。

覆盖主要列表页；export_rows 仅从授权数据范围取数（farm/area/personal），
组织范围由 service.scope 在入口校验。
"""

from __future__ import annotations

EXPORT_QUERIES = {
    "materials": "SELECT id,code,name,category,specification,unit,safety_stock,status,created_at FROM materials WHERE organization_id=%s{scope} ORDER BY id",
    "imports": "SELECT id,template_code,template_version,file_name,total_rows,passed_rows,failed_rows,status,imported_count,created_at FROM data_import_batches WHERE organization_id=%s{scope} ORDER BY id DESC",
    "farms": "SELECT id,code,name,status,created_at FROM farms WHERE organization_id=%s{scope} ORDER BY id",
    "areas": "SELECT id,code,name,farm_id,status,created_at FROM areas WHERE organization_id=%s{scope} ORDER BY id",
    "pond-groups": "SELECT id,code,name,area_id,description,created_at FROM pond_groups WHERE organization_id=%s{scope} ORDER BY id",
    "ponds": "SELECT id,code,name,species,capacity_mu,pond_status,status,created_at FROM ponds WHERE organization_id=%s{scope} ORDER BY id",
    "suppliers": "SELECT id,code,name,contact_name,phone,status,created_at FROM business_partners WHERE organization_id=%s AND partner_type='supplier'{scope} ORDER BY id",
    "customers": "SELECT id,code,name,contact_name,phone,status,created_at FROM business_partners WHERE organization_id=%s AND partner_type='customer'{scope} ORDER BY id",
    "business-settings": "SELECT id,code,name,group_code,value_text,status,created_at FROM business_settings WHERE organization_id=%s{scope} ORDER BY id",
    "batches": "SELECT id,code,name,species,pond_id,initial_quantity,initial_weight_kg,batch_status,status,stocked_at,created_at FROM production_batches WHERE organization_id=%s{scope} ORDER BY id",
    "samplings": "SELECT id,code,name,batch_id,pond_id,quantity,happened_at,status,created_at FROM production_documents WHERE organization_id=%s AND document_type='sampling'{scope} ORDER BY id",
    "transfers": "SELECT id,code,name,batch_id,pond_id,target_pond_id,quantity,happened_at,status,created_at FROM production_documents WHERE organization_id=%s AND document_type='transfer'{scope} ORDER BY id",
    "losses": "SELECT id,code,name,batch_id,pond_id,quantity,happened_at,note,status,created_at FROM production_documents WHERE organization_id=%s AND document_type='loss'{scope} ORDER BY id",
    "harvests": "SELECT id,code,name,batch_id,pond_id,quantity,happened_at,status,created_at FROM production_documents WHERE organization_id=%s AND document_type='harvest'{scope} ORDER BY id",
    "feed-plans": "SELECT id,code,name,pond_id,quantity,status,created_at FROM production_documents WHERE organization_id=%s AND document_type='feed_plan'{scope} ORDER BY id",
    "feed-tasks": "SELECT id,code,name,pond_id,assigned_user_id,planned_at,status,created_at FROM production_documents WHERE organization_id=%s AND document_type='feed_task'{scope} ORDER BY id",
    "feed-logs": "SELECT id,code,name,pond_id,material_id,quantity,happened_at,status,created_at FROM production_documents WHERE organization_id=%s AND document_type='feed_log'{scope} ORDER BY id",
    "daily-operations": "SELECT id,code,name,pond_id,happened_at,status,created_at FROM production_documents WHERE organization_id=%s AND document_type='daily_operation'{scope} ORDER BY id",
    "receipts": "SELECT id,code,name,warehouse_id,material_id,quantity,happened_at,status,created_at FROM warehouse_documents WHERE organization_id=%s AND document_type='receipt'{scope} ORDER BY id",
    "issues": "SELECT id,code,name,warehouse_id,material_id,quantity,happened_at,status,created_at FROM warehouse_documents WHERE organization_id=%s AND document_type='issue'{scope} ORDER BY id",
    "warehouse-transfers": "SELECT id,code,name,warehouse_id,target_warehouse_id,material_id,quantity,happened_at,status,created_at FROM warehouse_documents WHERE organization_id=%s AND document_type='transfer'{scope} ORDER BY id",
    "returns": "SELECT id,code,name,warehouse_id,material_id,quantity,happened_at,status,created_at FROM warehouse_documents WHERE organization_id=%s AND document_type='return'{scope} ORDER BY id",
    "stocktakes": "SELECT id,code,name,warehouse_id,material_id,quantity,happened_at,status,created_at FROM warehouse_documents WHERE organization_id=%s AND document_type='stocktake'{scope} ORDER BY id",
    "scraps": "SELECT id,code,name,warehouse_id,material_id,quantity,happened_at,reason,status,created_at FROM warehouse_documents WHERE organization_id=%s AND document_type='scrap'{scope} ORDER BY id",
    "inventory-ledger": "SELECT g.id,g.warehouse_id,g.material_id,g.source_type,g.source_id,g.quantity_delta,g.unit_cost,g.happened_at,g.created_at FROM inventory_ledger g JOIN warehouses w ON w.id=g.warehouse_id WHERE g.organization_id=%s{scope} ORDER BY g.id",
    "stock-alerts": "SELECT x.id,x.alert_key,x.warehouse_id,x.material_id,x.alert_type,x.status,x.resolution_note,x.created_at FROM warehouse_alert_actions x JOIN warehouses w ON w.id=x.warehouse_id WHERE x.organization_id=%s{scope} ORDER BY x.id",
    "purchase-orders": "SELECT id,code,name,supplier_id,material_id,warehouse_id,quantity,unit_price,total_amount,due_date,status,created_at FROM purchase_orders WHERE organization_id=%s{scope} ORDER BY id",
    "payables": "SELECT p.id,p.purchase_order_id,p.supplier_id,p.amount,p.paid_amount,p.due_date,p.status,o.code AS order_code FROM purchase_payables p JOIN purchase_orders o ON o.id=p.purchase_order_id WHERE p.organization_id=%s{scope} ORDER BY p.id",
    "payments": "SELECT p.id,p.code,p.name,p.payable_id,p.amount,p.paid_at,p.status,p.created_at,o.code AS order_code FROM purchase_payments p JOIN purchase_payables b ON b.id=p.payable_id JOIN purchase_orders o ON o.id=b.purchase_order_id WHERE p.organization_id=%s{scope} ORDER BY p.id",
    "sales-orders": "SELECT id,code,name,customer_id,pond_id,batch_id,species,quantity,unit,unit_price,total_amount,sold_at,due_date,status,created_at FROM sales_orders WHERE organization_id=%s{scope} ORDER BY id",
    "sales-deliveries": "SELECT d.id,d.code,d.name,d.sales_order_id,d.quantity,d.delivered_at,d.status,d.created_at,o.code AS order_code FROM sales_deliveries d JOIN sales_orders o ON o.id=d.sales_order_id WHERE d.organization_id=%s{scope} ORDER BY d.id",
    "receivables": "SELECT r.id,r.sales_order_id,r.customer_id,r.amount,r.received_amount,r.due_date,r.status,o.code AS order_code FROM sales_receivables r JOIN sales_orders o ON o.id=r.sales_order_id WHERE r.organization_id=%s{scope} ORDER BY r.id",
    "customer-receipts": "SELECT m.id,m.code,m.name,m.receivable_id,m.amount,m.received_at,m.receipt_method,m.status,m.created_at,o.code AS order_code FROM sales_receipts m JOIN sales_receivables r ON r.id=m.receivable_id JOIN sales_orders o ON o.id=r.sales_order_id WHERE m.organization_id=%s{scope} ORDER BY m.id",
    "expenses": "SELECT id,source_ref,amount,occurred_on,period_start,period_end,status,created_at FROM cost_entries WHERE organization_id=%s{scope} ORDER BY id",
    "cost-adjustments": "SELECT id,source_ref,amount,occurred_on,period_start,period_end,status,created_at FROM cost_entries WHERE organization_id=%s AND source_type='adjustment'{scope} ORDER BY id",
    "assets": "SELECT id,code,name,asset_type,original_value,salvage_value,useful_life_months,status,created_at FROM cost_assets WHERE organization_id=%s{scope} ORDER BY id",
    "leases": "SELECT id,code,name,asset_type,original_value,salvage_value,useful_life_months,status,created_at FROM cost_assets WHERE organization_id=%s AND asset_type='lease'{scope} ORDER BY id",
    "settlements": "SELECT id,code,name,period_start,period_end,income_amount,cost_amount,profit_amount,status,created_at FROM cost_settlements WHERE organization_id=%s{scope} ORDER BY id",
}

# 数据范围列：area scope 过滤列（None 表示该资源只按组织范围导出）。
EXPORT_AREA_COLUMNS = {
    "materials": "area_id", "farms": None, "areas": "id", "pond-groups": "area_id", "ponds": "area_id",
    "suppliers": "area_id", "customers": "area_id", "business-settings": "area_id",
    "batches": "area_id", "samplings": "area_id", "transfers": "area_id", "losses": "area_id",
    "harvests": "area_id", "feed-plans": "area_id", "feed-tasks": "area_id", "feed-logs": "area_id",
    "daily-operations": "area_id", "receipts": "area_id", "issues": "area_id", "warehouse-transfers": "area_id",
    "returns": "area_id", "stocktakes": "area_id", "scraps": "area_id", "inventory-ledger": "w.area_id",
    "stock-alerts": "w.area_id", "purchase-orders": "area_id", "payables": "o.area_id", "payments": "o.area_id",
    "sales-orders": "area_id", "sales-deliveries": "o.area_id", "receivables": "o.area_id",
    "customer-receipts": "o.area_id", "expenses": "area_id", "cost-adjustments": "area_id",
    "assets": "area_id", "leases": "area_id", "settlements": "area_id",
}

# personal scope 过滤列（created_by 等）。
EXPORT_PERSONAL_COLUMNS = {
    "materials": "created_by", "farms": "created_by", "areas": "created_by", "pond-groups": "created_by",
    "ponds": "created_by", "suppliers": "created_by", "customers": "created_by", "business-settings": "created_by",
    "batches": "created_by", "samplings": "created_by", "transfers": "created_by", "losses": "created_by",
    "harvests": "created_by", "feed-plans": "created_by", "feed-tasks": "created_by", "feed-logs": "created_by",
    "daily-operations": "created_by", "receipts": "created_by", "issues": "created_by", "warehouse-transfers": "created_by",
    "returns": "created_by", "stocktakes": "created_by", "scraps": "created_by", "inventory-ledger": "g.posted_by",
    "stock-alerts": "x.handled_by",
    "purchase-orders": "created_by", "payables": "o.created_by", "payments": "p.created_by",
    "sales-orders": "created_by", "sales-deliveries": "d.created_by", "receivables": "o.created_by",
    "customer-receipts": "m.created_by", "expenses": "created_by", "cost-adjustments": "created_by",
    "assets": "created_by", "leases": "created_by", "settlements": "created_by",
    "imports": "imported_by",
}
