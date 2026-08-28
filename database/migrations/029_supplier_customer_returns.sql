SET NAMES utf8mb4;
ALTER TABLE inventory_ledger MODIFY source_type ENUM('receipt','issue','return','purchase_return','sales_return','transfer_out','transfer_in','stocktake','scrap','correction') NOT NULL;

CREATE TABLE IF NOT EXISTS purchase_returns (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  source_receipt_id BIGINT UNSIGNED NOT NULL,
  payable_id BIGINT UNSIGNED NOT NULL,
  warehouse_id BIGINT UNSIGNED NOT NULL,
  material_id BIGINT UNSIGNED NOT NULL,
  inventory_lot_id BIGINT UNSIGNED NOT NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  quantity DECIMAL(18,3) NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  reason VARCHAR(500) NOT NULL,
  status ENUM('draft','submitted','verified','cancelled') NOT NULL DEFAULT 'draft',
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  created_by BIGINT UNSIGNED NOT NULL,
  verified_by BIGINT UNSIGNED NULL,
  verified_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id), UNIQUE KEY uq_purchase_returns_org_code (organization_id,code),
  KEY idx_purchase_returns_status (organization_id,status),
  FOREIGN KEY (organization_id) REFERENCES organizations(id), FOREIGN KEY (source_receipt_id) REFERENCES warehouse_documents(id),
  FOREIGN KEY (payable_id) REFERENCES purchase_payables(id), FOREIGN KEY (warehouse_id) REFERENCES warehouses(id),
  FOREIGN KEY (material_id) REFERENCES materials(id), FOREIGN KEY (inventory_lot_id) REFERENCES inventory_lots(id),
  FOREIGN KEY (created_by) REFERENCES users(id), FOREIGN KEY (verified_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS sales_returns (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  source_delivery_id BIGINT UNSIGNED NOT NULL,
  receivable_id BIGINT UNSIGNED NOT NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  quantity DECIMAL(18,3) NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  refund_amount DECIMAL(18,2) NOT NULL DEFAULT 0,
  reason VARCHAR(500) NOT NULL,
  status ENUM('draft','submitted','verified','cancelled') NOT NULL DEFAULT 'draft',
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  created_by BIGINT UNSIGNED NOT NULL,
  verified_by BIGINT UNSIGNED NULL,
  verified_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id), UNIQUE KEY uq_sales_returns_org_code (organization_id,code),
  KEY idx_sales_returns_status (organization_id,status),
  FOREIGN KEY (organization_id) REFERENCES organizations(id), FOREIGN KEY (source_delivery_id) REFERENCES sales_deliveries(id),
  FOREIGN KEY (receivable_id) REFERENCES sales_receivables(id), FOREIGN KEY (created_by) REFERENCES users(id), FOREIGN KEY (verified_by) REFERENCES users(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE purchase_payable_adjustments MODIFY source_receipt_id BIGINT UNSIGNED NULL;
ALTER TABLE purchase_payable_adjustments ADD COLUMN purchase_return_id BIGINT UNSIGNED NULL AFTER source_receipt_id;
ALTER TABLE purchase_payable_adjustments ADD UNIQUE KEY uq_purchase_payable_adjustments_return (purchase_return_id);
ALTER TABLE purchase_payable_adjustments ADD CONSTRAINT fk_purchase_payable_adjustments_return FOREIGN KEY (purchase_return_id) REFERENCES purchase_returns(id);
ALTER TABLE sales_receivable_adjustments MODIFY source_delivery_id BIGINT UNSIGNED NULL;
ALTER TABLE sales_receivable_adjustments ADD COLUMN sales_return_id BIGINT UNSIGNED NULL AFTER source_delivery_id;
ALTER TABLE sales_receivable_adjustments ADD UNIQUE KEY uq_sales_receivable_adjustments_return (sales_return_id);
ALTER TABLE sales_receivable_adjustments ADD CONSTRAINT fk_sales_receivable_adjustments_return FOREIGN KEY (sales_return_id) REFERENCES sales_returns(id);

INSERT INTO permissions (code,name,module_code,description) VALUES
 ('purchase.return.manage','办理采购退货','purchase','创建并提交供应商退货'),
 ('purchase.return.verify','核验采购退货','purchase','核验退货并冲减应付'),
 ('sales.return.manage','办理销售退货','sales','创建并提交客户退货'),
 ('sales.return.verify','核验销售退货','sales','核验退货并冲减应收')
ON DUPLICATE KEY UPDATE name=VALUES(name),description=VALUES(description);

INSERT IGNORE INTO role_permissions (role_id,permission_id)
SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.status='active' AND (
 (r.code='super_admin' AND p.code IN ('purchase.return.manage','purchase.return.verify','sales.return.manage','sales.return.verify')) OR
 (r.code='purchaser' AND p.code='purchase.return.manage') OR (r.code='sales_staff' AND p.code='sales.return.manage') OR
 (r.code='finance_staff' AND p.code IN ('purchase.return.verify','sales.return.verify'))
);

DELIMITER $$
CREATE TRIGGER purchase_returns_no_verified_update BEFORE UPDATE ON purchase_returns FOR EACH ROW
BEGIN IF OLD.status='verified' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='verified purchase return is immutable'; END IF; END$$
CREATE TRIGGER purchase_returns_no_formal_delete BEFORE DELETE ON purchase_returns FOR EACH ROW
BEGIN IF OLD.status<>'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='formal purchase return cannot be deleted'; END IF; END$$
CREATE TRIGGER sales_returns_no_verified_update BEFORE UPDATE ON sales_returns FOR EACH ROW
BEGIN IF OLD.status='verified' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='verified sales return is immutable'; END IF; END$$
CREATE TRIGGER sales_returns_no_formal_delete BEFORE DELETE ON sales_returns FOR EACH ROW
BEGIN IF OLD.status<>'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='formal sales return cannot be deleted'; END IF; END$$
DELIMITER ;
