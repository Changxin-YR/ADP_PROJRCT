SET NAMES utf8mb4;

CREATE TABLE sales_orders (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  farm_id BIGINT UNSIGNED NOT NULL,
  area_id BIGINT UNSIGNED NOT NULL,
  pond_id BIGINT UNSIGNED NOT NULL,
  batch_id BIGINT UNSIGNED NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  species VARCHAR(100) NOT NULL,
  quantity DECIMAL(18,3) NOT NULL,
  unit ENUM('kg','jin','tail') NOT NULL,
  unit_price DECIMAL(18,4) NOT NULL,
  total_amount DECIMAL(18,2) NOT NULL,
  sold_at DATE NOT NULL,
  due_date DATE NOT NULL,
  note VARCHAR(500) NULL,
  evidence_attachment_ids_json JSON NULL,
  status ENUM('draft','submitted','approved','partially_delivered','fully_delivered','closed','cancelled','disputed') NOT NULL DEFAULT 'draft',
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
  UNIQUE KEY uq_sales_orders_org_code (organization_id,code),
  KEY idx_sales_orders_scope_status (organization_id,farm_id,area_id,pond_id,status),
  CONSTRAINT fk_sales_orders_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_orders_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_orders_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_orders_pond FOREIGN KEY (pond_id) REFERENCES ponds(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_orders_batch FOREIGN KEY (batch_id) REFERENCES production_batches(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_orders_customer FOREIGN KEY (customer_id) REFERENCES business_partners(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_orders_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_orders_updated FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_orders_approved FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_orders_cancelled FOREIGN KEY (cancelled_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE sales_deliveries (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  sales_order_id BIGINT UNSIGNED NOT NULL,
  harvest_document_id BIGINT UNSIGNED NOT NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  quantity DECIMAL(18,3) NOT NULL,
  delivered_at DATETIME NOT NULL,
  transport_info VARCHAR(500) NULL,
  acceptance_note VARCHAR(500) NULL,
  evidence_attachment_ids_json JSON NULL,
  correction_of_id BIGINT UNSIGNED NULL,
  correction_reason VARCHAR(500) NULL,
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
  UNIQUE KEY uq_sales_deliveries_org_code (organization_id,code),
  UNIQUE KEY uq_sales_deliveries_harvest (harvest_document_id),
  UNIQUE KEY uq_sales_deliveries_correction (correction_of_id),
  KEY idx_sales_deliveries_order_status (sales_order_id,status),
  CONSTRAINT fk_sales_deliveries_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_deliveries_order FOREIGN KEY (sales_order_id) REFERENCES sales_orders(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_deliveries_harvest FOREIGN KEY (harvest_document_id) REFERENCES production_documents(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_deliveries_correction FOREIGN KEY (correction_of_id) REFERENCES sales_deliveries(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_deliveries_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_deliveries_updated FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_deliveries_verified FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_deliveries_cancelled FOREIGN KEY (cancelled_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE sales_receivables (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  sales_order_id BIGINT UNSIGNED NOT NULL,
  source_delivery_id BIGINT UNSIGNED NOT NULL,
  customer_id BIGINT UNSIGNED NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  received_amount DECIMAL(18,2) NOT NULL DEFAULT 0,
  due_date DATE NOT NULL,
  status ENUM('unpaid','partial','settled','overpaid','disputed','bad_debt','cancelled') NOT NULL DEFAULT 'unpaid',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_sales_receivables_delivery (source_delivery_id),
  UNIQUE KEY uq_sales_receivables_idempotency (idempotency_key),
  KEY idx_sales_receivables_customer_status_due (customer_id,status,due_date),
  CONSTRAINT fk_sales_receivables_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_receivables_order FOREIGN KEY (sales_order_id) REFERENCES sales_orders(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_receivables_delivery FOREIGN KEY (source_delivery_id) REFERENCES sales_deliveries(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_receivables_customer FOREIGN KEY (customer_id) REFERENCES business_partners(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE sales_receivable_adjustments (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  receivable_id BIGINT UNSIGNED NOT NULL,
  source_delivery_id BIGINT UNSIGNED NOT NULL,
  amount_delta DECIMAL(18,2) NOT NULL,
  reason VARCHAR(500) NOT NULL,
  created_by BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_sales_receivable_adjustments_delivery (source_delivery_id),
  CONSTRAINT fk_sales_receivable_adjustments_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_receivable_adjustments_receivable FOREIGN KEY (receivable_id) REFERENCES sales_receivables(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_receivable_adjustments_delivery FOREIGN KEY (source_delivery_id) REFERENCES sales_deliveries(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_receivable_adjustments_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE sales_receipts (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  receivable_id BIGINT UNSIGNED NOT NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  received_at DATE NOT NULL,
  receipt_method VARCHAR(32) NOT NULL,
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
  UNIQUE KEY uq_sales_receipts_org_code (organization_id,code),
  KEY idx_sales_receipts_receivable_status (receivable_id,status),
  CONSTRAINT fk_sales_receipts_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_receipts_receivable FOREIGN KEY (receivable_id) REFERENCES sales_receivables(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_receipts_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_receipts_updated FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_receipts_verified FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_receipts_cancelled FOREIGN KEY (cancelled_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE sales_receipt_reversals (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  receipt_id BIGINT UNSIGNED NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  reversal_reason VARCHAR(500) NOT NULL,
  evidence_attachment_ids_json JSON NOT NULL,
  created_by BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_sales_receipt_reversals_receipt (receipt_id),
  CONSTRAINT fk_sales_receipt_reversals_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_receipt_reversals_receipt FOREIGN KEY (receipt_id) REFERENCES sales_receipts(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_receipt_reversals_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO permissions (code,name,module_code,description) VALUES
  ('sales.view','查看销售业务','sales','查看授权范围销售单、交付和进度'),
  ('sales.manage','办理销售业务','sales','创建、编辑、提交销售与交付单'),
  ('sales.verify','审批销售业务','sales','审批销售单并核验交付'),
  ('finance.receivable.view','查看应收账款','finance','查看客户应收、收款和余额'),
  ('finance.receipt.manage','登记收款','finance','创建、编辑和提交收款记录'),
  ('finance.receipt.verify','核验收款','finance','核验收款并核销应收余额')
ON DUPLICATE KEY UPDATE name=VALUES(name),description=VALUES(description);

INSERT IGNORE INTO role_permissions (role_id,permission_id)
SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.status='active' AND (
  (r.code='super_admin' AND p.code IN ('sales.view','sales.manage','sales.verify','finance.receivable.view','finance.receipt.manage','finance.receipt.verify')) OR
  (r.code='sales_staff' AND p.code IN ('sales.view','sales.manage')) OR
  (r.code IN ('breed_manager','breed_worker') AND p.code='sales.view') OR
  (r.code='finance_staff' AND p.code IN ('sales.view','sales.verify','finance.receivable.view','finance.receipt.manage','finance.receipt.verify'))
);

DELIMITER $$
CREATE TRIGGER sales_orders_no_formal_delete BEFORE DELETE ON sales_orders FOR EACH ROW
BEGIN IF OLD.status<>'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='formal sales order cannot be deleted'; END IF; END$$
CREATE TRIGGER sales_orders_no_approved_business_update BEFORE UPDATE ON sales_orders FOR EACH ROW
BEGIN IF OLD.status IN ('approved','partially_delivered','fully_delivered','closed','cancelled','disputed') AND (NOT (OLD.code<=>NEW.code) OR NOT (OLD.customer_id<=>NEW.customer_id) OR NOT (OLD.pond_id<=>NEW.pond_id) OR NOT (OLD.batch_id<=>NEW.batch_id) OR NOT (OLD.quantity<=>NEW.quantity) OR NOT (OLD.unit_price<=>NEW.unit_price) OR NOT (OLD.due_date<=>NEW.due_date)) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='approved sales order business fields are immutable'; END IF; END$$
CREATE TRIGGER sales_deliveries_no_verified_update BEFORE UPDATE ON sales_deliveries FOR EACH ROW
BEGIN IF OLD.status='verified' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='verified sales delivery is immutable'; END IF; END$$
CREATE TRIGGER sales_deliveries_no_formal_delete BEFORE DELETE ON sales_deliveries FOR EACH ROW
BEGIN IF OLD.status<>'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='formal sales delivery cannot be deleted'; END IF; END$$
CREATE TRIGGER sales_receivables_no_delete BEFORE DELETE ON sales_receivables FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='sales receivable is append-only'$$
CREATE TRIGGER sales_receivables_no_business_update BEFORE UPDATE ON sales_receivables FOR EACH ROW
BEGIN IF NOT (OLD.organization_id<=>NEW.organization_id) OR NOT (OLD.sales_order_id<=>NEW.sales_order_id) OR NOT (OLD.source_delivery_id<=>NEW.source_delivery_id) OR NOT (OLD.customer_id<=>NEW.customer_id) OR NOT (OLD.idempotency_key<=>NEW.idempotency_key) OR NOT (OLD.amount<=>NEW.amount) OR NOT (OLD.due_date<=>NEW.due_date) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='sales receivable business fields are immutable'; END IF; END$$
CREATE TRIGGER sales_receivable_adjustments_no_update BEFORE UPDATE ON sales_receivable_adjustments FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='sales receivable adjustment is append-only'$$
CREATE TRIGGER sales_receivable_adjustments_no_delete BEFORE DELETE ON sales_receivable_adjustments FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='sales receivable adjustment is append-only'$$
CREATE TRIGGER sales_receipts_no_verified_update BEFORE UPDATE ON sales_receipts FOR EACH ROW
BEGIN IF OLD.status='verified' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='verified sales receipt is immutable'; END IF; END$$
CREATE TRIGGER sales_receipts_no_formal_delete BEFORE DELETE ON sales_receipts FOR EACH ROW
BEGIN IF OLD.status<>'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='formal sales receipt cannot be deleted'; END IF; END$$
CREATE TRIGGER sales_receipt_reversals_no_update BEFORE UPDATE ON sales_receipt_reversals FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='sales receipt reversal is append-only'$$
CREATE TRIGGER sales_receipt_reversals_no_delete BEFORE DELETE ON sales_receipt_reversals FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='sales receipt reversal is append-only'$$
DELIMITER ;
