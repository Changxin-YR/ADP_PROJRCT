SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS cost_categories (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(100) NOT NULL,
  default_nature ENUM('direct','public') NOT NULL,
  default_allocation_driver ENUM('area','equipment_count','runtime_hours','direct_input','direct_consumption','work_scope','manual_ratio','equal') NOT NULL,
  sort_order INT NOT NULL DEFAULT 0,
  status ENUM('active','disabled') NOT NULL DEFAULT 'active',
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_cost_categories_code (code),
  KEY idx_cost_categories_status_sort (status, sort_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cost_entries (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  category_id BIGINT UNSIGNED NOT NULL,
  amount DECIMAL(14,2) NOT NULL,
  occurred_on DATE NOT NULL,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  status ENUM('draft','pending','confirmed','void') NOT NULL DEFAULT 'draft',
  cost_nature ENUM('direct','public') NOT NULL,
  source_type VARCHAR(64) NOT NULL,
  source_ref VARCHAR(128) NOT NULL,
  source_detail_json JSON NULL,
  target_type ENUM('farm','area','group','pond','batch') NULL,
  target_id BIGINT UNSIGNED NULL,
  reversal_of_id BIGINT UNSIGNED NULL,
  created_by BIGINT UNSIGNED NULL,
  confirmed_by BIGINT UNSIGNED NULL,
  confirmed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  KEY idx_cost_entries_period_status (period_start, period_end, status),
  KEY idx_cost_entries_category_period (category_id, occurred_on),
  KEY idx_cost_entries_source (source_type, source_ref),
  CONSTRAINT fk_cost_entries_category FOREIGN KEY (category_id) REFERENCES cost_categories(id),
  CONSTRAINT fk_cost_entries_reversal FOREIGN KEY (reversal_of_id) REFERENCES cost_entries(id),
  CONSTRAINT fk_cost_entries_created_by FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
  CONSTRAINT fk_cost_entries_confirmed_by FOREIGN KEY (confirmed_by) REFERENCES users(id) ON DELETE SET NULL,
  CONSTRAINT ck_cost_entries_period CHECK (period_start <= period_end),
  CONSTRAINT ck_cost_entries_reversal_amount CHECK (reversal_of_id IS NULL OR amount < 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cost_allocation_rule_versions (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  version_no INT UNSIGNED NOT NULL,
  effective_from DATE NOT NULL,
  effective_to DATE NULL,
  status ENUM('draft','active','retired') NOT NULL,
  change_reason VARCHAR(500) NOT NULL,
  created_by BIGINT UNSIGNED NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_cost_rule_versions_no (version_no),
  KEY idx_cost_rule_versions_effective (status, effective_from, effective_to),
  CONSTRAINT fk_cost_rule_versions_user FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE SET NULL,
  CONSTRAINT ck_cost_rule_versions_dates CHECK (effective_to IS NULL OR effective_from <= effective_to)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS cost_allocation_rules (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  version_id BIGINT UNSIGNED NOT NULL,
  category_id BIGINT UNSIGNED NOT NULL,
  driver ENUM('area','equipment_count','runtime_hours','direct_input','direct_consumption','work_scope','manual_ratio','equal') NOT NULL,
  fallback_driver ENUM('equal') NOT NULL DEFAULT 'equal',
  manual_ratio_json JSON NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_cost_rules_version_category (version_id, category_id),
  CONSTRAINT fk_cost_rules_version FOREIGN KEY (version_id) REFERENCES cost_allocation_rule_versions(id),
  CONSTRAINT fk_cost_rules_category FOREIGN KEY (category_id) REFERENCES cost_categories(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO cost_categories (code, name, default_nature, default_allocation_driver, sort_order) VALUES
('pond_rent','塘租','public','area',10),
('equipment','设备','public','equipment_count',20),
('infrastructure','基础建设','public','area',30),
('labor','人工','public','work_scope',40),
('electricity','电费','public','runtime_hours',50),
('seed','苗种','direct','direct_input',60),
('feed','饲料','direct','direct_consumption',70),
('health','动保','direct','direct_consumption',80),
('other','其他费用','public','equal',90)
ON DUPLICATE KEY UPDATE name=VALUES(name), default_nature=VALUES(default_nature), default_allocation_driver=VALUES(default_allocation_driver), sort_order=VALUES(sort_order), status='active';

INSERT INTO permissions (code, name, module_code, description) VALUES
('cost.view','查看成本核算','cost','查看九类成本、来源明细与分摊规则'),
('cost.allocation.manage','管理成本分摊规则','cost','创建新的成本分摊规则版本')
ON DUPLICATE KEY UPDATE name=VALUES(name), module_code=VALUES(module_code), description=VALUES(description);

INSERT IGNORE INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r CROSS JOIN permissions p
WHERE (p.code='cost.view' AND r.code IN ('super_admin','breed_manager','finance_staff'))
   OR (p.code='cost.allocation.manage' AND r.code IN ('super_admin','finance_staff'));

INSERT INTO cost_entries (category_id, amount, occurred_on, period_start, period_end, status, cost_nature, source_type, source_ref, source_detail_json, confirmed_at)
SELECT c.id, seed.amount, '2026-08-15', '2026-01-01', '2026-08-15', 'confirmed', c.default_nature, 'legacy_import', 'LEGACY-INIT-2026', JSON_OBJECT('note','从既有成本构成页面迁移的初始化口径'), CURRENT_TIMESTAMP
FROM cost_categories c JOIN (
  SELECT 'pond_rent' code, 120000.00 amount UNION ALL SELECT 'equipment',38000.00 UNION ALL
  SELECT 'infrastructure',46000.00 UNION ALL SELECT 'labor',144000.00 UNION ALL
  SELECT 'electricity',42000.00 UNION ALL SELECT 'seed',96000.00 UNION ALL
  SELECT 'feed',128000.00 UNION ALL SELECT 'health',26000.00 UNION ALL SELECT 'other',32000.00
) seed ON seed.code=c.code
WHERE NOT EXISTS (SELECT 1 FROM cost_entries WHERE source_type='legacy_import' AND source_ref='LEGACY-INIT-2026');

INSERT INTO cost_allocation_rule_versions (version_no, effective_from, effective_to, status, change_reason)
SELECT 1, '2026-01-01', NULL, 'active', '初始化九类成本分摊规则'
WHERE NOT EXISTS (SELECT 1 FROM cost_allocation_rule_versions WHERE version_no=1);

INSERT IGNORE INTO cost_allocation_rules (version_id, category_id, driver)
SELECT v.id, c.id, c.default_allocation_driver
FROM cost_allocation_rule_versions v CROSS JOIN cost_categories c
WHERE v.version_no=1 AND c.status='active';
