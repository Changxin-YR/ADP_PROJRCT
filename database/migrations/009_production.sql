SET NAMES utf8mb4;

CREATE TABLE production_batches (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  farm_id BIGINT UNSIGNED NOT NULL,
  area_id BIGINT UNSIGNED NOT NULL,
  pond_id BIGINT UNSIGNED NOT NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  species VARCHAR(100) NOT NULL,
  initial_quantity DECIMAL(18,3) NOT NULL DEFAULT 0,
  initial_weight_kg DECIMAL(18,3) NOT NULL DEFAULT 0,
  stocked_at DATETIME NULL,
  expected_harvest_date DATE NULL,
  note VARCHAR(500) NULL,
  correction_of_id BIGINT UNSIGNED NULL,
  batch_status ENUM('stocked','farming','pending_settlement','closed') NOT NULL DEFAULT 'stocked',
  status ENUM('draft','submitted','verified','corrected','archived') NOT NULL DEFAULT 'draft',
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  created_by BIGINT UNSIGNED NOT NULL,
  updated_by BIGINT UNSIGNED NULL,
  verified_by BIGINT UNSIGNED NULL,
  verified_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_production_batches_org_code (organization_id, code),
  UNIQUE KEY uq_production_batches_correction (correction_of_id),
  KEY idx_production_batches_scope_status (organization_id, farm_id, area_id, pond_id, status),
  CONSTRAINT fk_production_batches_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_batches_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_batches_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_batches_pond FOREIGN KEY (pond_id) REFERENCES ponds(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_batches_correction FOREIGN KEY (correction_of_id) REFERENCES production_batches(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_batches_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_batches_updated FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_batches_verified FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE production_documents (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  farm_id BIGINT UNSIGNED NOT NULL,
  area_id BIGINT UNSIGNED NOT NULL,
  document_type ENUM('sampling','transfer','loss','harvest','feed_plan','feed_task','feed_log','daily_operation','correction') NOT NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  batch_id BIGINT UNSIGNED NULL,
  pond_id BIGINT UNSIGNED NOT NULL,
  target_pond_id BIGINT UNSIGNED NULL,
  material_id BIGINT UNSIGNED NULL,
  assigned_user_id BIGINT UNSIGNED NULL,
  feed_plan_id BIGINT UNSIGNED NULL,
  feed_task_id BIGINT UNSIGNED NULL,
  -- ponytail: Task 7 owns the material-issue table and will add this column's foreign key.
  material_issue_request_id BIGINT UNSIGNED NULL,
  quantity DECIMAL(18,3) NOT NULL DEFAULT 0,
  weight_kg DECIMAL(18,3) NOT NULL DEFAULT 0,
  happened_at DATETIME NULL,
  planned_at DATETIME NULL,
  note VARCHAR(500) NULL,
  payload_json JSON NULL,
  evidence_attachment_ids_json JSON NULL,
  correction_of_id BIGINT UNSIGNED NULL,
  status ENUM('draft','submitted','verified','corrected','archived') NOT NULL DEFAULT 'draft',
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  created_by BIGINT UNSIGNED NOT NULL,
  updated_by BIGINT UNSIGNED NULL,
  verified_by BIGINT UNSIGNED NULL,
  verified_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_production_documents_org_type_code (organization_id, document_type, code),
  UNIQUE KEY uq_production_documents_correction (correction_of_id),
  KEY idx_production_documents_scope_status (organization_id, farm_id, area_id, document_type, status),
  KEY idx_production_documents_batch_pond (batch_id, pond_id, happened_at),
  CONSTRAINT fk_production_documents_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_documents_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_documents_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_documents_batch FOREIGN KEY (batch_id) REFERENCES production_batches(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_documents_pond FOREIGN KEY (pond_id) REFERENCES ponds(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_documents_target_pond FOREIGN KEY (target_pond_id) REFERENCES ponds(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_documents_material FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_documents_assigned FOREIGN KEY (assigned_user_id) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_documents_feed_plan FOREIGN KEY (feed_plan_id) REFERENCES production_documents(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_documents_feed_task FOREIGN KEY (feed_task_id) REFERENCES production_documents(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_documents_correction FOREIGN KEY (correction_of_id) REFERENCES production_documents(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_documents_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_documents_updated FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_production_documents_verified FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE batch_stock_records (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  batch_id BIGINT UNSIGNED NOT NULL,
  pond_id BIGINT UNSIGNED NOT NULL,
  source_type ENUM('stocking','transfer_out','transfer_in','loss','harvest','correction') NOT NULL,
  source_id BIGINT UNSIGNED NOT NULL,
  line_no TINYINT UNSIGNED NOT NULL DEFAULT 1,
  quantity_delta DECIMAL(18,3) NOT NULL DEFAULT 0,
  weight_delta_kg DECIMAL(18,3) NOT NULL DEFAULT 0,
  happened_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  posted_by BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_batch_stock_source_line (source_type, source_id, line_no),
  KEY idx_batch_stock_batch_pond_time (batch_id, pond_id, happened_at, id),
  CONSTRAINT fk_batch_stock_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_batch_stock_batch FOREIGN KEY (batch_id) REFERENCES production_batches(id) ON DELETE RESTRICT,
  CONSTRAINT fk_batch_stock_pond FOREIGN KEY (pond_id) REFERENCES ponds(id) ON DELETE RESTRICT,
  CONSTRAINT fk_batch_stock_posted FOREIGN KEY (posted_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO permissions (code, name, module_code, description) VALUES
  ('production.view', '查看生产业务', 'production', '查看授权范围内批次和生产记录'),
  ('production.manage', '维护生产业务', 'production', '新建、编辑、提交和删除生产草稿'),
  ('production.verify', '核验生产业务', 'production', '核验生产记录并形成正式流水')
ON DUPLICATE KEY UPDATE name = VALUES(name), description = VALUES(description);

INSERT IGNORE INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE r.status = 'active' AND (
  (r.code IN ('super_admin','breed_manager') AND p.code IN ('production.view','production.manage','production.verify')) OR
  (r.code = 'breed_worker' AND p.code IN ('production.view','production.manage')) OR
  (r.code IN ('warehouse_manager','finance_staff','sales_staff') AND p.code = 'production.view')
);

DELIMITER $$
CREATE TRIGGER production_batches_no_verified_update BEFORE UPDATE ON production_batches FOR EACH ROW
BEGIN IF OLD.status IN ('verified','corrected','archived') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'verified production batch is immutable'; END IF; END$$
CREATE TRIGGER production_batches_no_formal_delete BEFORE DELETE ON production_batches FOR EACH ROW
BEGIN IF OLD.status <> 'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'formal production batch cannot be deleted'; END IF; END$$
CREATE TRIGGER production_documents_no_verified_update BEFORE UPDATE ON production_documents FOR EACH ROW
BEGIN IF OLD.status IN ('verified','corrected','archived') THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'verified production document is immutable'; END IF; END$$
CREATE TRIGGER production_documents_no_formal_delete BEFORE DELETE ON production_documents FOR EACH ROW
BEGIN IF OLD.status <> 'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'formal production document cannot be deleted'; END IF; END$$
CREATE TRIGGER batch_stock_records_no_update BEFORE UPDATE ON batch_stock_records FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'batch stock ledger is append-only'$$
CREATE TRIGGER batch_stock_records_no_delete BEFORE DELETE ON batch_stock_records FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'batch stock ledger is append-only'$$
DELIMITER ;
