SET NAMES utf8mb4;

CREATE TABLE warehouses (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  farm_id BIGINT UNSIGNED NOT NULL,
  area_id BIGINT UNSIGNED NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  location VARCHAR(255) NULL,
  status ENUM('active','disabled') NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_warehouses_org_code (organization_id, code),
  CONSTRAINT fk_warehouses_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouses_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouses_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE inventory_lots (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  material_id BIGINT UNSIGNED NOT NULL,
  supplier_id BIGINT UNSIGNED NULL,
  lot_no VARCHAR(80) NOT NULL,
  production_date DATE NULL,
  expiry_date DATE NULL,
  unit_cost DECIMAL(18,4) NOT NULL DEFAULT 0,
  status ENUM('available','quarantined','expired','closed') NOT NULL DEFAULT 'available',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_inventory_lots_org_material_lot (organization_id, material_id, lot_no),
  CONSTRAINT fk_inventory_lots_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_inventory_lots_material FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE RESTRICT,
  CONSTRAINT fk_inventory_lots_supplier FOREIGN KEY (supplier_id) REFERENCES business_partners(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE warehouse_documents (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  farm_id BIGINT UNSIGNED NOT NULL,
  area_id BIGINT UNSIGNED NULL,
  document_type ENUM('receipt','issue_request','issue','return','transfer','stocktake','scrap','correction') NOT NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  warehouse_id BIGINT UNSIGNED NOT NULL,
  target_warehouse_id BIGINT UNSIGNED NULL,
  material_id BIGINT UNSIGNED NOT NULL,
  inventory_lot_id BIGINT UNSIGNED NULL,
  source_document_id BIGINT UNSIGNED NULL,
  purchase_order_id BIGINT UNSIGNED NULL,
  pond_id BIGINT UNSIGNED NULL,
  batch_id BIGINT UNSIGNED NULL,
  task_id BIGINT UNSIGNED NULL,
  scene VARCHAR(40) NULL,
  quantity DECIMAL(18,3) NOT NULL DEFAULT 0,
  unit_cost DECIMAL(18,4) NOT NULL DEFAULT 0,
  lot_no VARCHAR(80) NULL,
  production_date DATE NULL,
  expiry_date DATE NULL,
  location VARCHAR(255) NULL,
  reason VARCHAR(500) NULL,
  override_reason VARCHAR(500) NULL,
  happened_at DATETIME NULL,
  evidence_attachment_ids_json JSON NULL,
  note VARCHAR(500) NULL,
  correction_reason VARCHAR(500) NULL,
  correction_of_id BIGINT UNSIGNED NULL,
  received_quantity DECIMAL(18,3) NULL,
  receipt_difference_reason VARCHAR(500) NULL,
  status ENUM('draft','submitted','in_transit','verified','corrected','cancelled','archived') NOT NULL DEFAULT 'draft',
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  created_by BIGINT UNSIGNED NOT NULL,
  updated_by BIGINT UNSIGNED NULL,
  dispatched_by BIGINT UNSIGNED NULL,
  dispatched_at DATETIME NULL,
  received_by BIGINT UNSIGNED NULL,
  received_at DATETIME NULL,
  cancellation_reason VARCHAR(500) NULL,
  cancelled_by BIGINT UNSIGNED NULL,
  cancelled_at DATETIME NULL,
  verified_by BIGINT UNSIGNED NULL,
  verified_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_warehouse_documents_org_type_code (organization_id, document_type, code),
  UNIQUE KEY uq_warehouse_documents_correction (correction_of_id),
  KEY idx_warehouse_documents_scope_status (organization_id, farm_id, area_id, document_type, status),
  CONSTRAINT fk_warehouse_documents_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_warehouse FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_target FOREIGN KEY (target_warehouse_id) REFERENCES warehouses(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_material FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_lot FOREIGN KEY (inventory_lot_id) REFERENCES inventory_lots(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_source FOREIGN KEY (source_document_id) REFERENCES warehouse_documents(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_pond FOREIGN KEY (pond_id) REFERENCES ponds(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_batch FOREIGN KEY (batch_id) REFERENCES production_batches(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_task FOREIGN KEY (task_id) REFERENCES production_documents(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_correction FOREIGN KEY (correction_of_id) REFERENCES warehouse_documents(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_updated FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_dispatched FOREIGN KEY (dispatched_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_received FOREIGN KEY (received_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_cancelled FOREIGN KEY (cancelled_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_documents_verified FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE inventory_ledger (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  warehouse_id BIGINT UNSIGNED NOT NULL,
  material_id BIGINT UNSIGNED NOT NULL,
  inventory_lot_id BIGINT UNSIGNED NOT NULL,
  source_type ENUM('receipt','issue','return','transfer_out','transfer_in','stocktake','scrap','correction') NOT NULL,
  source_id BIGINT UNSIGNED NOT NULL,
  line_no SMALLINT UNSIGNED NOT NULL,
  quantity_delta DECIMAL(18,3) NOT NULL,
  unit_cost DECIMAL(18,4) NOT NULL DEFAULT 0,
  pond_id BIGINT UNSIGNED NULL,
  batch_id BIGINT UNSIGNED NULL,
  happened_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  posted_by BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_inventory_ledger_source_line (source_type, source_id, line_no),
  KEY idx_inventory_ledger_balance (warehouse_id, material_id, inventory_lot_id, happened_at, id),
  CONSTRAINT fk_inventory_ledger_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_inventory_ledger_warehouse FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE RESTRICT,
  CONSTRAINT fk_inventory_ledger_material FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE RESTRICT,
  CONSTRAINT fk_inventory_ledger_lot FOREIGN KEY (inventory_lot_id) REFERENCES inventory_lots(id) ON DELETE RESTRICT,
  CONSTRAINT fk_inventory_ledger_pond FOREIGN KEY (pond_id) REFERENCES ponds(id) ON DELETE RESTRICT,
  CONSTRAINT fk_inventory_ledger_batch FOREIGN KEY (batch_id) REFERENCES production_batches(id) ON DELETE RESTRICT,
  CONSTRAINT fk_inventory_ledger_posted FOREIGN KEY (posted_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE warehouse_alert_actions (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  alert_key VARCHAR(180) NOT NULL,
  warehouse_id BIGINT UNSIGNED NOT NULL,
  material_id BIGINT UNSIGNED NOT NULL,
  inventory_lot_id BIGINT UNSIGNED NOT NULL,
  alert_type ENUM('low_stock','expiring','expired','stocktake_difference','inactive') NOT NULL,
  condition_fingerprint CHAR(64) NOT NULL,
  status ENUM('handled','closed') NOT NULL DEFAULT 'handled',
  action_code ENUM('replenish','transfer','scrap','recheck','threshold') NOT NULL,
  resolution_note VARCHAR(500) NOT NULL,
  handled_by BIGINT UNSIGNED NOT NULL,
  handled_at DATETIME NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_warehouse_alert_actions_key (alert_key),
  CONSTRAINT fk_warehouse_alert_actions_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_alert_actions_warehouse FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_alert_actions_material FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_alert_actions_lot FOREIGN KEY (inventory_lot_id) REFERENCES inventory_lots(id) ON DELETE RESTRICT,
  CONSTRAINT fk_warehouse_alert_actions_user FOREIGN KEY (handled_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE production_documents
  ADD CONSTRAINT fk_production_documents_material_issue_request
    FOREIGN KEY (material_issue_request_id) REFERENCES warehouse_documents(id) ON DELETE RESTRICT;

INSERT INTO permissions (code,name,module_code,description) VALUES
  ('warehouse.view','查看仓储业务','warehouse','查看授权范围库存与单据'),
  ('warehouse.manage','办理仓储业务','warehouse','新建、编辑、提交和删除仓储草稿'),
  ('warehouse.verify','核验仓储业务','warehouse','核验仓储单据并形成正式库存流水')
ON DUPLICATE KEY UPDATE name=VALUES(name),description=VALUES(description);

INSERT IGNORE INTO role_permissions (role_id,permission_id)
SELECT r.id,p.id FROM roles r CROSS JOIN permissions p WHERE r.status='active' AND (
  (r.code IN ('super_admin','warehouse_manager') AND p.code IN ('warehouse.view','warehouse.manage','warehouse.verify')) OR
  (r.code IN ('breed_manager','breed_worker','purchaser','finance_staff') AND p.code='warehouse.view')
);

DELIMITER $$
CREATE TRIGGER warehouse_documents_no_verified_update BEFORE UPDATE ON warehouse_documents FOR EACH ROW
BEGIN IF OLD.status IN ('verified','corrected','archived') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='verified warehouse document is immutable'; END IF; END$$
CREATE TRIGGER warehouse_documents_no_formal_delete BEFORE DELETE ON warehouse_documents FOR EACH ROW
BEGIN IF OLD.status<>'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='formal warehouse document cannot be deleted'; END IF; END$$
CREATE TRIGGER inventory_ledger_no_update BEFORE UPDATE ON inventory_ledger FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='inventory ledger is append-only'$$
CREATE TRIGGER inventory_ledger_no_delete BEFORE DELETE ON inventory_ledger FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='inventory ledger is append-only'$$
DELIMITER ;
