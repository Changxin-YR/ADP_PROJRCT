SET NAMES utf8mb4;

CREATE TABLE data_import_batches (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  template_code VARCHAR(64) NOT NULL,
  template_version VARCHAR(32) NOT NULL,
  file_name VARCHAR(255) NOT NULL,
  file_sha256 CHAR(64) NOT NULL,
  total_rows INT UNSIGNED NOT NULL,
  passed_rows INT UNSIGNED NOT NULL,
  failed_rows INT UNSIGNED NOT NULL,
  status ENUM('invalid','ready','imported','undone') NOT NULL,
  preview_rows_json JSON NOT NULL,
  errors_json JSON NOT NULL,
  imported_count INT UNSIGNED NOT NULL DEFAULT 0,
  imported_by BIGINT UNSIGNED NOT NULL,
  imported_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_data_import_file (organization_id,template_code,file_sha256),
  KEY idx_data_import_scope_created (organization_id,created_at),
  CONSTRAINT fk_data_import_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_data_import_user FOREIGN KEY (imported_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE data_import_items (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  import_batch_id BIGINT UNSIGNED NOT NULL,
  entity_type VARCHAR(64) NOT NULL,
  entity_id BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_data_import_item (import_batch_id,entity_type,entity_id),
  CONSTRAINT fk_data_import_item_batch FOREIGN KEY (import_batch_id) REFERENCES data_import_batches(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE data_export_audits (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  resource_code VARCHAR(64) NOT NULL,
  format ENUM('xlsx','pdf') NOT NULL,
  filters_json JSON NOT NULL,
  row_count INT UNSIGNED NOT NULL,
  request_id VARCHAR(32) NOT NULL,
  exported_by BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_data_export_scope_created (organization_id,created_at),
  CONSTRAINT fk_data_export_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_data_export_user FOREIGN KEY (exported_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE attachments
  ADD UNIQUE KEY uq_attachments_entity_hash (organization_id,entity_type,entity_id,sha256);

INSERT INTO permissions (code,name,module_code,description) VALUES
  ('data_exchange.view','查看数据交换','data_exchange','查看模板、导入批次和附件'),
  ('data_exchange.import','执行批量导入','data_exchange','预校验并确认授权范围内的批量导入'),
  ('data_exchange.export','导出业务数据','data_exchange','按授权数据范围导出 Excel 或 PDF'),
  ('attachment.manage','管理业务附件','data_exchange','上传和下载授权业务记录附件')
ON DUPLICATE KEY UPDATE name=VALUES(name),description=VALUES(description);

INSERT IGNORE INTO role_permissions (role_id,permission_id)
SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
WHERE r.status='active' AND (
  (r.code='super_admin' AND p.code IN ('data_exchange.view','data_exchange.import','data_exchange.export','attachment.manage')) OR
  (r.code IN ('breed_manager','warehouse_manager','purchaser','finance','sales_staff') AND p.code IN ('data_exchange.view','data_exchange.export','attachment.manage'))
);

DELIMITER $$
CREATE TRIGGER data_export_audits_no_update BEFORE UPDATE ON data_export_audits FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='data export audit is append-only'$$
CREATE TRIGGER data_export_audits_no_delete BEFORE DELETE ON data_export_audits FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='data export audit is append-only'$$
CREATE TRIGGER data_import_batches_no_delete BEFORE DELETE ON data_import_batches FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='data import history cannot be deleted'$$
DELIMITER ;
