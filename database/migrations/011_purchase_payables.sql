SET NAMES utf8mb4;

CREATE TABLE purchase_orders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  farm_id BIGINT UNSIGNED NOT NULL,
  area_id BIGINT UNSIGNED NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  supplier_id BIGINT UNSIGNED NOT NULL,
  material_id BIGINT UNSIGNED NOT NULL,
  warehouse_id BIGINT UNSIGNED NOT NULL,
  quantity DECIMAL(18,3) NOT NULL,
  unit_price DECIMAL(18,4) NOT NULL,
  total_amount DECIMAL(18,2) NOT NULL,
  expected_delivery_date DATE NULL,
  due_date DATE NOT NULL,
  note VARCHAR(500) NULL,
  evidence_attachment_ids_json JSON NULL,
  status ENUM('draft','submitted','approved','partially_received','fully_received','closed','cancelled','disputed') NOT NULL DEFAULT 'draft',
  cancellation_reason VARCHAR(500) NULL,
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  created_by BIGINT UNSIGNED NOT NULL,
  updated_by BIGINT UNSIGNED NULL,
  approved_by BIGINT UNSIGNED NULL,
  approved_at DATETIME NULL,
  cancelled_by BIGINT UNSIGNED NULL,
  cancelled_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_purchase_orders_org_code (organization_id,code),
  KEY idx_purchase_orders_scope_status (organization_id,farm_id,area_id,status),
  CONSTRAINT fk_purchase_orders_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_orders_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_orders_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_orders_supplier FOREIGN KEY (supplier_id) REFERENCES business_partners(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_orders_material FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_orders_warehouse FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_orders_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_orders_updated FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_orders_approved FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_orders_cancelled FOREIGN KEY (cancelled_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE warehouse_documents
  ADD CONSTRAINT fk_warehouse_documents_purchase_order
  FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders(id) ON DELETE RESTRICT;

CREATE TABLE purchase_payables (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  purchase_order_id BIGINT UNSIGNED NOT NULL,
  source_receipt_id BIGINT UNSIGNED NOT NULL,
  supplier_id BIGINT UNSIGNED NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  paid_amount DECIMAL(18,2) NOT NULL DEFAULT 0,
  due_date DATE NOT NULL,
  status ENUM('unpaid','partial','settled','disputed','cancelled') NOT NULL DEFAULT 'unpaid',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_purchase_payables_receipt (source_receipt_id),
  UNIQUE KEY uq_purchase_payables_idempotency (idempotency_key),
  KEY idx_purchase_payables_supplier_status_due (supplier_id,status,due_date),
  CONSTRAINT fk_purchase_payables_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_payables_order FOREIGN KEY (purchase_order_id) REFERENCES purchase_orders(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_payables_receipt FOREIGN KEY (source_receipt_id) REFERENCES warehouse_documents(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_payables_supplier FOREIGN KEY (supplier_id) REFERENCES business_partners(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE purchase_payments (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  payable_id BIGINT UNSIGNED NOT NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  paid_at DATE NOT NULL,
  note VARCHAR(500) NULL,
  evidence_attachment_ids_json JSON NULL,
  status ENUM('draft','submitted','verified','cancelled') NOT NULL DEFAULT 'draft',
  cancellation_reason VARCHAR(500) NULL,
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  created_by BIGINT UNSIGNED NOT NULL,
  updated_by BIGINT UNSIGNED NULL,
  verified_by BIGINT UNSIGNED NULL,
  verified_at DATETIME NULL,
  cancelled_by BIGINT UNSIGNED NULL,
  cancelled_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_purchase_payments_org_code (organization_id,code),
  KEY idx_purchase_payments_payable_status (payable_id,status),
  CONSTRAINT fk_purchase_payments_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_payments_payable FOREIGN KEY (payable_id) REFERENCES purchase_payables(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_payments_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_payments_updated FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_payments_verified FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_payments_cancelled FOREIGN KEY (cancelled_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO permissions (code,name,module_code,description) VALUES
  ('purchase.view','查看采购业务','purchase','查看授权范围采购单和到货进度'),
  ('purchase.manage','办理采购业务','purchase','创建、编辑和提交采购单'),
  ('purchase.verify','审批采购业务','purchase','审批或有痕取消采购单'),
  ('finance.payable.view','查看应付账款','finance','查看采购应付、付款和余额'),
  ('finance.payment.manage','登记付款','finance','创建、编辑和提交付款记录'),
  ('finance.payment.verify','核验付款','finance','核验付款并核销应付余额')
ON DUPLICATE KEY UPDATE name=VALUES(name),description=VALUES(description);

INSERT IGNORE INTO role_permissions (role_id,permission_id)
SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.status='active' AND (
  (r.code='super_admin' AND p.code IN ('purchase.view','purchase.manage','purchase.verify','finance.payable.view','finance.payment.manage','finance.payment.verify')) OR
  (r.code='purchaser' AND p.code IN ('purchase.view','purchase.manage')) OR
  (r.code='warehouse_manager' AND p.code='purchase.view') OR
  (r.code='finance_staff' AND p.code IN ('purchase.view','purchase.verify','finance.payable.view','finance.payment.manage','finance.payment.verify'))
);

DELIMITER $$
CREATE TRIGGER purchase_orders_no_formal_delete BEFORE DELETE ON purchase_orders FOR EACH ROW
BEGIN IF OLD.status<>'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='formal purchase order cannot be deleted'; END IF; END$$
CREATE TRIGGER purchase_orders_no_approved_business_update BEFORE UPDATE ON purchase_orders FOR EACH ROW
BEGIN
  IF OLD.status IN ('approved','partially_received','fully_received','closed','cancelled','disputed') AND
    (NOT (OLD.code<=>NEW.code) OR NOT (OLD.supplier_id<=>NEW.supplier_id) OR NOT (OLD.material_id<=>NEW.material_id) OR
     NOT (OLD.warehouse_id<=>NEW.warehouse_id) OR NOT (OLD.quantity<=>NEW.quantity) OR NOT (OLD.unit_price<=>NEW.unit_price) OR
     NOT (OLD.due_date<=>NEW.due_date)) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='approved purchase order business fields are immutable';
  END IF;
END$$
CREATE TRIGGER purchase_payables_no_delete BEFORE DELETE ON purchase_payables FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='purchase payable is append-only'$$
CREATE TRIGGER purchase_payments_no_verified_update BEFORE UPDATE ON purchase_payments FOR EACH ROW
BEGIN IF OLD.status='verified' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='verified purchase payment is immutable'; END IF; END$$
CREATE TRIGGER purchase_payments_no_formal_delete BEFORE DELETE ON purchase_payments FOR EACH ROW
BEGIN IF OLD.status<>'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='formal purchase payment cannot be deleted'; END IF; END$$
DELIMITER ;
