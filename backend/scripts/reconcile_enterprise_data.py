from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pymysql


ROOT = Path(__file__).resolve().parents[2]
CHECK_NAMES = (
    "foreign_key_orphans", "duplicate_unique_keys", "illegal_workflow_state",
    "negative_inventory", "negative_batch_stock", "batch_stock_source_mismatch",
    "payable_payment_difference", "receivable_receipt_difference",
    "cost_allocation_difference", "work_item_state_mismatch", "self_approval",
    "missing_required_voucher", "immutability_trigger_missing", "migration_checksum_drift",
)

STATIC_CHECKS = {
    "illegal_workflow_state": """
        SELECT COUNT(*) issue_count FROM (
          SELECT id FROM production_batches WHERE status='verified' AND (verified_by IS NULL OR verified_at IS NULL)
          UNION ALL SELECT id FROM production_documents WHERE status='verified' AND (verified_by IS NULL OR verified_at IS NULL)
          UNION ALL SELECT id FROM warehouse_documents WHERE status='verified' AND (verified_by IS NULL OR verified_at IS NULL)
          UNION ALL SELECT id FROM purchase_orders WHERE status IN ('approved','partially_received','fully_received','closed') AND (approved_by IS NULL OR approved_at IS NULL)
          UNION ALL SELECT id FROM purchase_payments WHERE status='verified' AND (verified_by IS NULL OR verified_at IS NULL)
          UNION ALL SELECT id FROM sales_orders WHERE status IN ('approved','partially_delivered','fully_delivered','closed') AND (approved_by IS NULL OR approved_at IS NULL)
          UNION ALL SELECT id FROM sales_deliveries WHERE status='verified' AND (verified_by IS NULL OR verified_at IS NULL)
          UNION ALL SELECT id FROM sales_receipts WHERE status='verified' AND (verified_by IS NULL OR verified_at IS NULL)
          UNION ALL SELECT id FROM cost_entries WHERE status IN ('verified','confirmed') AND source_type NOT IN ('legacy_import','warehouse_ledger','asset_depreciation') AND (verified_by IS NULL OR verified_at IS NULL)
          UNION ALL SELECT id FROM cost_assets WHERE status IN ('verified','confirmed') AND (verified_by IS NULL OR verified_at IS NULL)
          UNION ALL SELECT id FROM cost_settlements WHERE status IN ('verified','confirmed') AND (verified_by IS NULL OR verified_at IS NULL)
          UNION ALL SELECT id FROM pond_status_change_requests WHERE status='verified' AND (verified_by IS NULL OR verified_at IS NULL)
          UNION ALL
          SELECT so.id FROM sales_orders so LEFT JOIN (
            SELECT sales_order_id,SUM(quantity) delivered FROM sales_deliveries WHERE status='verified' GROUP BY sales_order_id
          ) d ON d.sales_order_id=so.id
          WHERE so.status IN ('approved','partially_delivered','fully_delivered','closed') AND NOT (
            (so.status='approved' AND COALESCE(d.delivered,0)=0) OR
            (so.status='partially_delivered' AND COALESCE(d.delivered,0)>0 AND COALESCE(d.delivered,0)<so.quantity) OR
            (so.status IN ('fully_delivered','closed') AND COALESCE(d.delivered,0)=so.quantity)
          )
          UNION ALL
          SELECT po.id FROM purchase_orders po LEFT JOIN (
            SELECT purchase_order_id,SUM(quantity) received FROM warehouse_documents WHERE document_type='receipt' AND status='verified' GROUP BY purchase_order_id
          ) r ON r.purchase_order_id=po.id
          WHERE po.status IN ('approved','partially_received','fully_received','closed') AND NOT (
            (po.status='approved' AND COALESCE(r.received,0)=0) OR
            (po.status='partially_received' AND COALESCE(r.received,0)>0 AND COALESCE(r.received,0)<po.quantity) OR
            (po.status IN ('fully_received','closed') AND COALESCE(r.received,0)=po.quantity)
          )
        ) invalid_states
    """,
    "negative_inventory": """
        SELECT COUNT(*) issue_count FROM (
          SELECT warehouse_id,material_id,inventory_lot_id FROM inventory_ledger
          GROUP BY warehouse_id,material_id,inventory_lot_id HAVING SUM(quantity_delta)<0
        ) negative_balances
    """,
    "negative_batch_stock": """
        SELECT COUNT(*) issue_count FROM (
          SELECT batch_id,pond_id FROM batch_stock_records GROUP BY batch_id,pond_id
          HAVING SUM(quantity_delta)<0 OR SUM(weight_delta_kg)<0
        ) negative_balances
    """,
    "batch_stock_source_mismatch": """
        SELECT COUNT(*) issue_count FROM (
          SELECT b.id FROM production_batches b LEFT JOIN batch_stock_records l
            ON l.source_type='stocking' AND l.source_id=b.id
          WHERE b.status='verified' AND b.correction_of_id IS NULL GROUP BY b.id,b.initial_quantity,b.initial_weight_kg
          HAVING COUNT(l.id)<>1 OR COALESCE(SUM(l.quantity_delta),0)<>b.initial_quantity OR COALESCE(SUM(l.weight_delta_kg),0)<>b.initial_weight_kg
          UNION ALL
          SELECT d.id FROM production_documents d LEFT JOIN batch_stock_records l ON l.source_id=d.id
          WHERE d.status='verified' AND d.correction_of_id IS NULL AND d.document_type IN ('transfer','loss','harvest')
          GROUP BY d.id,d.document_type HAVING COUNT(l.id)<>IF(d.document_type='transfer',2,1)
        ) source_mismatches
    """,
    "payable_payment_difference": """
        SELECT COUNT(*) issue_count FROM purchase_payables p
        LEFT JOIN (
          SELECT pay.payable_id,SUM(CASE WHEN pay.status='verified' AND rev.id IS NULL THEN pay.amount ELSE 0 END) total
          FROM purchase_payments pay LEFT JOIN purchase_payment_reversals rev ON rev.payment_id=pay.id GROUP BY pay.payable_id
        ) paid ON paid.payable_id=p.id WHERE p.paid_amount<>COALESCE(paid.total,0)
    """,
    "receivable_receipt_difference": """
        SELECT COUNT(*) issue_count FROM sales_receivables r
        LEFT JOIN (
          SELECT receipt.receivable_id,SUM(CASE WHEN receipt.status='verified' AND rev.id IS NULL THEN receipt.amount ELSE 0 END) total
          FROM sales_receipts receipt LEFT JOIN sales_receipt_reversals rev ON rev.receipt_id=receipt.id GROUP BY receipt.receivable_id
        ) received ON received.receivable_id=r.id WHERE r.received_amount<>COALESCE(received.total,0)
    """,
    "cost_allocation_difference": """
        SELECT COUNT(*) issue_count FROM cost_allocation_runs run LEFT JOIN (
          SELECT run_id,SUM(amount) detail_total FROM cost_allocation_details GROUP BY run_id
        ) detail ON detail.run_id=run.id
        WHERE run.source_total<>run.allocated_total OR run.allocated_total<>COALESCE(detail.detail_total,0)
    """,
    "work_item_state_mismatch": """
        SELECT COUNT(*) issue_count FROM work_items WHERE
          (status='completed' AND (completed_by IS NULL OR completed_at IS NULL)) OR
          (status='cancelled' AND (cancelled_by IS NULL OR cancelled_at IS NULL)) OR
          (status IN ('pending','claimed','in_progress','escalated') AND (completed_at IS NOT NULL OR cancelled_at IS NOT NULL))
    """,
    "self_approval": """
        SELECT COUNT(*) issue_count FROM (
          SELECT id FROM production_batches WHERE verified_by IN (created_by,COALESCE(updated_by,0))
          UNION ALL SELECT id FROM production_documents WHERE verified_by IN (created_by,COALESCE(updated_by,0))
          UNION ALL SELECT id FROM warehouse_documents WHERE verified_by IN (created_by,COALESCE(updated_by,0))
          UNION ALL SELECT id FROM purchase_orders WHERE approved_by IN (created_by,COALESCE(updated_by,0))
          UNION ALL SELECT id FROM purchase_payments WHERE verified_by IN (created_by,COALESCE(updated_by,0))
          UNION ALL SELECT id FROM sales_orders WHERE approved_by IN (created_by,COALESCE(updated_by,0))
          UNION ALL SELECT id FROM sales_deliveries WHERE verified_by IN (created_by,COALESCE(updated_by,0))
          UNION ALL SELECT id FROM sales_receipts WHERE verified_by IN (created_by,COALESCE(updated_by,0))
          UNION ALL SELECT id FROM cost_entries WHERE verified_by IN (created_by,COALESCE(updated_by,0))
          UNION ALL SELECT id FROM cost_assets WHERE verified_by IN (created_by,COALESCE(updated_by,0))
          UNION ALL SELECT id FROM cost_settlements WHERE verified_by IN (created_by,COALESCE(updated_by,0))
          UNION ALL SELECT id FROM pond_status_change_requests WHERE verified_by=requested_by
        ) self_approved
    """,
    "missing_required_voucher": """
        SELECT COUNT(*) issue_count FROM (
          SELECT id FROM purchase_payments WHERE status='verified' AND COALESCE(JSON_LENGTH(evidence_attachment_ids_json),0)=0
          UNION ALL SELECT id FROM sales_receipts WHERE status='verified' AND COALESCE(JSON_LENGTH(evidence_attachment_ids_json),0)=0
          UNION ALL SELECT id FROM sales_deliveries WHERE status='verified' AND COALESCE(JSON_LENGTH(evidence_attachment_ids_json),0)=0
          UNION ALL SELECT id FROM cost_entries WHERE status IN ('verified','confirmed') AND source_type='manual' AND COALESCE(JSON_LENGTH(evidence_attachment_ids_json),0)=0
          UNION ALL SELECT id FROM cost_assets WHERE status IN ('verified','confirmed') AND COALESCE(JSON_LENGTH(evidence_attachment_ids_json),0)=0
        ) missing_vouchers
    """,
    "immutability_trigger_missing": """
        SELECT 20-COUNT(*) issue_count FROM information_schema.TRIGGERS WHERE TRIGGER_SCHEMA=DATABASE() AND TRIGGER_NAME IN (
          'audit_logs_no_update','audit_logs_no_delete','record_revisions_no_update','record_revisions_no_delete',
          'production_batches_no_verified_update','production_documents_no_verified_update','batch_stock_records_no_update','batch_stock_records_no_delete',
          'warehouse_documents_no_verified_update','inventory_ledger_no_update','inventory_ledger_no_delete',
          'purchase_orders_no_approved_business_update','purchase_payments_no_verified_update','purchase_payables_no_delete',
          'sales_orders_no_approved_business_update','sales_deliveries_no_verified_update','sales_receipts_no_verified_update','sales_receivables_no_business_update',
          'cost_entries_no_formal_update','pond_status_requests_no_formal_update')
    """,
}


def _identifier(value: str) -> str:
    return "`" + value.replace("`", "``") + "`"


def _count(cursor: Any, query: str) -> int:
    cursor.execute(query)
    return int((cursor.fetchone() or {}).get("issue_count", 0))


def foreign_key_orphans(cursor: Any) -> int:
    cursor.execute("SELECT TABLE_NAME,COLUMN_NAME,REFERENCED_TABLE_NAME,REFERENCED_COLUMN_NAME FROM information_schema.KEY_COLUMN_USAGE WHERE TABLE_SCHEMA=DATABASE() AND REFERENCED_TABLE_NAME IS NOT NULL")
    total = 0
    for row in cursor.fetchall():
        table, column = _identifier(row["TABLE_NAME"]), _identifier(row["COLUMN_NAME"])
        parent, parent_column = _identifier(row["REFERENCED_TABLE_NAME"]), _identifier(row["REFERENCED_COLUMN_NAME"])
        total += _count(cursor, f"SELECT COUNT(*) issue_count FROM {table} child LEFT JOIN {parent} parent ON child.{column}=parent.{parent_column} WHERE child.{column} IS NOT NULL AND parent.{parent_column} IS NULL")
    return total


def duplicate_unique_keys(cursor: Any) -> int:
    cursor.execute("SELECT TABLE_NAME,INDEX_NAME,GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX) columns_csv FROM information_schema.STATISTICS WHERE TABLE_SCHEMA=DATABASE() AND NON_UNIQUE=0 AND INDEX_NAME<>'PRIMARY' AND COLUMN_NAME IS NOT NULL GROUP BY TABLE_NAME,INDEX_NAME")
    total = 0
    for row in cursor.fetchall():
        columns = [_identifier(item) for item in row["columns_csv"].split(",")]
        present = " AND ".join(f"{column} IS NOT NULL" for column in columns)
        grouped = ",".join(columns)
        query = f"SELECT COUNT(*) issue_count FROM (SELECT 1 FROM {_identifier(row['TABLE_NAME'])} WHERE {present} GROUP BY {grouped} HAVING COUNT(*)>1) duplicate_groups"
        total += _count(cursor, query)
    return total


def compare_migration_checksums(recorded: dict[str, str], migration_dir: Path) -> list[str]:
    expected: dict[str, set[str]] = {}
    for path in sorted(migration_dir.glob("[0-9][0-9][0-9]_*.sql")):
        if path.name.startswith("000_"):
            continue
        content = path.read_bytes()
        lf_content = content.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        expected[path.stem] = {
            hashlib.sha256(content).hexdigest(),
            hashlib.sha256(lf_content).hexdigest(),
            hashlib.sha256(lf_content.replace(b"\n", b"\r\n")).hexdigest(),
        }
    issues = [f"{version}: missing registration" for version in expected.keys() - recorded.keys()]
    issues += [f"{version}: unknown registration" for version in recorded.keys() - expected.keys()]
    issues += [f"{version}: checksum mismatch" for version in expected.keys() & recorded.keys() if recorded[version] not in expected[version]]
    return sorted(issues)


def reconcile(connection: Any, migration_dir: Path) -> dict[str, Any]:
    checks: dict[str, int] = {}
    with connection.cursor() as cursor:
        checks["foreign_key_orphans"] = foreign_key_orphans(cursor)
        checks["duplicate_unique_keys"] = duplicate_unique_keys(cursor)
        for name, query in STATIC_CHECKS.items():
            checks[name] = _count(cursor, query)
        cursor.execute("SELECT version,checksum FROM schema_migrations")
        recorded = {str(row["version"]): str(row["checksum"]) for row in cursor.fetchall()}
    checks["migration_checksum_drift"] = len(compare_migration_checksums(recorded, migration_dir))
    total = sum(checks.values())
    return {"ok": total == 0, "total_issues": total, "checks": {name: checks[name] for name in CHECK_NAMES}}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run read-only ADP enterprise data reconciliation")
    parser.add_argument("--database", default=os.environ.get("MYSQL_DATABASE", "adp_auth"))
    parser.add_argument("--migrations", type=Path, default=ROOT / "database" / "migrations")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    connection = pymysql.connect(host=os.environ.get("MYSQL_HOST", "127.0.0.1"), port=int(os.environ.get("MYSQL_PORT", "3306")), user=os.environ.get("MYSQL_USER", "adp_dev"), password=os.environ.get("MYSQL_PASSWORD", ""), database=args.database, charset="utf8mb4", cursorclass=pymysql.cursors.DictCursor)
    try:
        result = reconcile(connection, args.migrations)
    finally:
        connection.close()
    payload = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload + "\n", encoding="utf-8")
    print(payload)
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
