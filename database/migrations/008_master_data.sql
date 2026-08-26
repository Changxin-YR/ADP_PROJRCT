SET NAMES utf8mb4;

ALTER TABLE farms
  MODIFY status ENUM('active','disabled','draft','submitted','verified','archived') NOT NULL DEFAULT 'active',
  ADD COLUMN created_by BIGINT UNSIGNED NULL AFTER row_version,
  ADD COLUMN updated_by BIGINT UNSIGNED NULL AFTER created_by,
  ADD CONSTRAINT fk_farms_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_farms_updated_by FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT;
UPDATE farms SET status = 'verified' WHERE status = 'active';
UPDATE farms SET status = 'archived' WHERE status = 'disabled';
ALTER TABLE farms
  MODIFY status ENUM('draft','submitted','verified','archived') NOT NULL DEFAULT 'draft';

ALTER TABLE areas
  MODIFY status ENUM('active','disabled','draft','submitted','verified','archived') NOT NULL DEFAULT 'active',
  ADD COLUMN row_version INT UNSIGNED NOT NULL DEFAULT 1 AFTER status,
  ADD COLUMN created_by BIGINT UNSIGNED NULL AFTER row_version,
  ADD COLUMN updated_by BIGINT UNSIGNED NULL AFTER created_by,
  ADD CONSTRAINT fk_areas_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_areas_updated_by FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT;
UPDATE areas SET status = 'verified' WHERE status = 'active';
UPDATE areas SET status = 'archived' WHERE status = 'disabled';
ALTER TABLE areas
  MODIFY status ENUM('draft','submitted','verified','archived') NOT NULL DEFAULT 'draft';

ALTER TABLE pond_groups
  ADD COLUMN description VARCHAR(500) NULL AFTER name,
  ADD COLUMN updated_by BIGINT UNSIGNED NULL AFTER created_by,
  ADD CONSTRAINT fk_pond_groups_updated_by FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT;

ALTER TABLE ponds
  ADD COLUMN description VARCHAR(500) NULL AFTER name,
  ADD COLUMN location_text VARCHAR(255) NULL AFTER description,
  ADD COLUMN species VARCHAR(100) NULL AFTER location_text,
  ADD COLUMN manager_name VARCHAR(80) NULL AFTER species,
  ADD COLUMN pond_status ENUM('build','stocked','farming','rest','clean','rebuild') NOT NULL DEFAULT 'build' AFTER capacity_mu,
  ADD COLUMN updated_by BIGINT UNSIGNED NULL AFTER created_by,
  ADD CONSTRAINT fk_ponds_updated_by FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT;

CREATE TABLE materials (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  farm_id BIGINT UNSIGNED NULL,
  area_id BIGINT UNSIGNED NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  category VARCHAR(64) NULL,
  specification VARCHAR(120) NULL,
  unit VARCHAR(32) NULL,
  safety_stock DECIMAL(18,3) NOT NULL DEFAULT 0,
  shelf_life_days INT UNSIGNED NULL,
  default_supplier_id BIGINT UNSIGNED NULL,
  status ENUM('draft','submitted','verified','archived') NOT NULL DEFAULT 'draft',
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  created_by BIGINT UNSIGNED NOT NULL,
  updated_by BIGINT UNSIGNED NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_materials_organization_code (organization_id, code),
  KEY idx_materials_scope_status (organization_id, farm_id, area_id, status),
  CONSTRAINT fk_materials_organization FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_materials_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  CONSTRAINT fk_materials_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_materials_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_materials_updated_by FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE business_partners (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  farm_id BIGINT UNSIGNED NULL,
  area_id BIGINT UNSIGNED NULL,
  partner_type ENUM('supplier','customer') NOT NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  contact_name VARCHAR(80) NULL,
  phone VARCHAR(32) NULL,
  address VARCHAR(255) NULL,
  settlement_days INT UNSIGNED NOT NULL DEFAULT 0,
  credit_limit DECIMAL(18,2) NOT NULL DEFAULT 0,
  note VARCHAR(500) NULL,
  status ENUM('draft','submitted','verified','archived') NOT NULL DEFAULT 'draft',
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  created_by BIGINT UNSIGNED NOT NULL,
  updated_by BIGINT UNSIGNED NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_business_partners_org_type_code (organization_id, partner_type, code),
  KEY idx_business_partners_scope_status (organization_id, farm_id, area_id, status),
  CONSTRAINT fk_business_partners_organization FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_business_partners_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  CONSTRAINT fk_business_partners_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_business_partners_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_business_partners_updated_by FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE materials
  ADD CONSTRAINT fk_materials_default_supplier FOREIGN KEY (default_supplier_id)
    REFERENCES business_partners(id) ON DELETE RESTRICT;

CREATE TABLE business_settings (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  farm_id BIGINT UNSIGNED NULL,
  area_id BIGINT UNSIGNED NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  group_code VARCHAR(64) NOT NULL,
  value_text VARCHAR(1000) NOT NULL,
  note VARCHAR(500) NULL,
  status ENUM('draft','submitted','verified','archived') NOT NULL DEFAULT 'draft',
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  created_by BIGINT UNSIGNED NOT NULL,
  updated_by BIGINT UNSIGNED NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_business_settings_organization_code (organization_id, code),
  KEY idx_business_settings_scope_status (organization_id, farm_id, area_id, status),
  CONSTRAINT fk_business_settings_organization FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_business_settings_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  CONSTRAINT fk_business_settings_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_business_settings_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_business_settings_updated_by FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO permissions (code, name, module_code, description) VALUES
  ('master_data.view', '查看主数据', 'master_data', '查看授权范围内的主数据'),
  ('master_data.manage', '维护主数据', 'master_data', '新建、编辑、提交和删除未提交草稿'),
  ('master_data.verify', '核验主数据', 'master_data', '核验提交后的主数据并永久锁定'),
  ('master_data.farms.manage', '维护基地', 'master_data', '维护基地档案'),
  ('master_data.areas.manage', '维护区域', 'master_data', '维护区域档案'),
  ('master_data.pond_groups.manage', '维护塘口分组', 'master_data', '维护塘口分组'),
  ('master_data.ponds.manage', '维护塘口', 'master_data', '维护塘口档案'),
  ('master_data.materials.manage', '维护物料', 'master_data', '维护物料档案'),
  ('master_data.suppliers.manage', '维护供应商', 'master_data', '维护供应商档案'),
  ('master_data.customers.manage', '维护客户', 'master_data', '维护客户档案')
ON DUPLICATE KEY UPDATE name = VALUES(name), description = VALUES(description);

INSERT IGNORE INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE r.status = 'active' AND (
  (p.code = 'master_data.view') OR
  (r.code = 'super_admin' AND p.code IN ('master_data.manage','master_data.verify')) OR
  (r.code = 'breed_manager' AND p.code IN ('master_data.farms.manage','master_data.areas.manage','master_data.pond_groups.manage','master_data.ponds.manage','master_data.verify')) OR
  (r.code = 'warehouse_manager' AND p.code = 'master_data.materials.manage') OR
  (r.code = 'purchaser' AND p.code = 'master_data.suppliers.manage') OR
  (r.code = 'sales_staff' AND p.code = 'master_data.customers.manage')
);

DELIMITER $$
CREATE TRIGGER farms_no_formal_delete BEFORE DELETE ON farms FOR EACH ROW
BEGIN IF OLD.status <> 'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'formal master data cannot be deleted'; END IF; END$$
CREATE TRIGGER areas_no_formal_delete BEFORE DELETE ON areas FOR EACH ROW
BEGIN IF OLD.status <> 'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'formal master data cannot be deleted'; END IF; END$$
CREATE TRIGGER pond_groups_no_formal_delete BEFORE DELETE ON pond_groups FOR EACH ROW
BEGIN IF OLD.status <> 'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'formal master data cannot be deleted'; END IF; END$$
CREATE TRIGGER ponds_no_formal_delete BEFORE DELETE ON ponds FOR EACH ROW
BEGIN IF OLD.status <> 'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'formal master data cannot be deleted'; END IF; END$$
CREATE TRIGGER materials_no_formal_delete BEFORE DELETE ON materials FOR EACH ROW
BEGIN IF OLD.status <> 'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'formal master data cannot be deleted'; END IF; END$$
CREATE TRIGGER business_partners_no_formal_delete BEFORE DELETE ON business_partners FOR EACH ROW
BEGIN IF OLD.status <> 'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'formal master data cannot be deleted'; END IF; END$$
CREATE TRIGGER business_settings_no_formal_delete BEFORE DELETE ON business_settings FOR EACH ROW
BEGIN IF OLD.status <> 'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'formal master data cannot be deleted'; END IF; END$$
DELIMITER ;
