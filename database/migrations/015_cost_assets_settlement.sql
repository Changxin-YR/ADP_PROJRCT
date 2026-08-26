SET NAMES utf8mb4;
DROP TRIGGER IF EXISTS cost_entries_no_posted_update;
DROP TRIGGER IF EXISTS cost_entries_no_formal_delete;
ALTER TABLE cost_entries
  ADD COLUMN organization_id BIGINT UNSIGNED NULL AFTER id,
  ADD COLUMN farm_id BIGINT UNSIGNED NULL AFTER organization_id,
  ADD COLUMN area_id BIGINT UNSIGNED NULL AFTER farm_id,
  ADD COLUMN row_version INT UNSIGNED NOT NULL DEFAULT 1 AFTER status,
  ADD COLUMN evidence_attachment_ids_json JSON NULL AFTER target_id,
  ADD COLUMN updated_by BIGINT UNSIGNED NULL AFTER created_by,
  ADD COLUMN verified_by BIGINT UNSIGNED NULL AFTER updated_by,
  ADD COLUMN verified_at DATETIME NULL AFTER verified_by,
  MODIFY status ENUM('draft','pending','submitted','verified','confirmed','reversed','void') NOT NULL DEFAULT 'draft';
UPDATE cost_entries SET status='submitted' WHERE status='pending';
UPDATE cost_entries ce
JOIN organizations o ON o.code='default'
JOIN farms f ON f.organization_id=o.id AND f.code='default-farm'
SET ce.organization_id=o.id,ce.farm_id=f.id
WHERE ce.organization_id IS NULL;
ALTER TABLE cost_entries
  MODIFY organization_id BIGINT UNSIGNED NOT NULL,
  MODIFY farm_id BIGINT UNSIGNED NOT NULL,
  MODIFY status ENUM('draft','submitted','verified','confirmed','reversed','void') NOT NULL DEFAULT 'draft',
  ADD KEY idx_cost_entries_scope_status (organization_id,farm_id,area_id,status),
  ADD UNIQUE KEY uq_cost_entries_reversal (reversal_of_id),
  ADD CONSTRAINT fk_cost_entries_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_cost_entries_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_cost_entries_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_cost_entries_updated FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_cost_entries_verified FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT;
CREATE TABLE cost_assets (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  farm_id BIGINT UNSIGNED NOT NULL,
  area_id BIGINT UNSIGNED NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  asset_type ENUM('equipment','infrastructure','lease') NOT NULL,
  category_id BIGINT UNSIGNED NOT NULL,
  purchase_date DATE NOT NULL,
  original_value DECIMAL(18,2) NOT NULL,
  salvage_value DECIMAL(18,2) NOT NULL DEFAULT 0,
  useful_life_months INT UNSIGNED NOT NULL,
  depreciation_start_date DATE NOT NULL,
  allocation_driver ENUM('area','equipment_count','runtime_hours','work_scope','manual_ratio','equal') NOT NULL DEFAULT 'equal',
  target_type ENUM('farm','area','group','pond','batch') NULL,
  target_id BIGINT UNSIGNED NULL,
  note VARCHAR(500) NULL,
  evidence_attachment_ids_json JSON NULL,
  status ENUM('draft','submitted','verified','confirmed','retired','disposed','cancelled') NOT NULL DEFAULT 'draft',
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  created_by BIGINT UNSIGNED NOT NULL,
  updated_by BIGINT UNSIGNED NULL,
  verified_by BIGINT UNSIGNED NULL,
  verified_at DATETIME NULL,
  confirmed_by BIGINT UNSIGNED NULL,
  confirmed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_cost_assets_org_code (organization_id,code),
  KEY idx_cost_assets_scope_status (organization_id,farm_id,area_id,status),
  CONSTRAINT fk_cost_assets_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_assets_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_assets_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_assets_category FOREIGN KEY (category_id) REFERENCES cost_categories(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_assets_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_assets_updated FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_assets_verified FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_assets_confirmed FOREIGN KEY (confirmed_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT ck_cost_assets_values CHECK (original_value>0 AND salvage_value>=0 AND salvage_value<original_value AND useful_life_months>0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE cost_depreciation_entries (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  asset_id BIGINT UNSIGNED NOT NULL,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  cost_entry_id BIGINT UNSIGNED NOT NULL,
  created_by BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_cost_depreciation_asset_period (asset_id,period_start,period_end),
  CONSTRAINT fk_cost_depreciation_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_depreciation_asset FOREIGN KEY (asset_id) REFERENCES cost_assets(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_depreciation_entry FOREIGN KEY (cost_entry_id) REFERENCES cost_entries(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_depreciation_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE cost_allocation_runs (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  farm_id BIGINT UNSIGNED NOT NULL,
  area_id BIGINT UNSIGNED NULL,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  rule_version_id BIGINT UNSIGNED NOT NULL,
  result_version INT UNSIGNED NOT NULL,
  source_total DECIMAL(18,2) NOT NULL,
  allocated_total DECIMAL(18,2) NOT NULL,
  fallback_count INT UNSIGNED NOT NULL DEFAULT 0,
  participant_snapshot_json JSON NOT NULL,
  status ENUM('completed','superseded') NOT NULL DEFAULT 'completed',
  created_by BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_cost_allocation_period_version (organization_id,farm_id,area_id,period_start,period_end,result_version),
  CONSTRAINT fk_cost_allocation_run_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_allocation_run_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_allocation_run_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_allocation_run_rule FOREIGN KEY (rule_version_id) REFERENCES cost_allocation_rule_versions(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_allocation_run_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT ck_cost_allocation_totals CHECK (source_total=allocated_total)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
CREATE TABLE cost_allocation_details (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  run_id BIGINT UNSIGNED NOT NULL,
  cost_entry_id BIGINT UNSIGNED NOT NULL,
  category_id BIGINT UNSIGNED NOT NULL,
  pond_id BIGINT UNSIGNED NOT NULL,
  batch_id BIGINT UNSIGNED NULL,
  amount DECIMAL(18,2) NOT NULL,
  driver VARCHAR(32) NOT NULL,
  driver_value DECIMAL(18,4) NOT NULL DEFAULT 0,
  fallback_used TINYINT(1) NOT NULL DEFAULT 0,
  source_snapshot_json JSON NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_cost_allocation_detail_target (run_id,cost_entry_id,pond_id,batch_id),
  CONSTRAINT fk_cost_allocation_detail_run FOREIGN KEY (run_id) REFERENCES cost_allocation_runs(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_allocation_detail_entry FOREIGN KEY (cost_entry_id) REFERENCES cost_entries(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_allocation_detail_category FOREIGN KEY (category_id) REFERENCES cost_categories(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_allocation_detail_pond FOREIGN KEY (pond_id) REFERENCES ponds(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_allocation_detail_batch FOREIGN KEY (batch_id) REFERENCES production_batches(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE cost_settlements (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  farm_id BIGINT UNSIGNED NOT NULL,
  area_id BIGINT UNSIGNED NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  allocation_run_id BIGINT UNSIGNED NOT NULL,
  income_amount DECIMAL(18,2) NOT NULL,
  cost_amount DECIMAL(18,2) NOT NULL,
  profit_amount DECIMAL(18,2) NOT NULL,
  status ENUM('draft','submitted','verified','confirmed','reversed','cancelled') NOT NULL DEFAULT 'draft',
  active_area_key BIGINT UNSIGNED GENERATED ALWAYS AS (IFNULL(area_id,0)) STORED,
  active_period_lock TINYINT UNSIGNED GENERATED ALWAYS AS (IF(status='reversed',NULL,1)) STORED,
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  reversal_reason VARCHAR(500) NULL,
  created_by BIGINT UNSIGNED NOT NULL,
  updated_by BIGINT UNSIGNED NULL,
  verified_by BIGINT UNSIGNED NULL,
  verified_at DATETIME NULL,
  confirmed_by BIGINT UNSIGNED NULL,
  confirmed_at DATETIME NULL,
  reversed_by BIGINT UNSIGNED NULL,
  reversed_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_cost_settlements_org_code (organization_id,code),
  UNIQUE KEY uq_cost_settlements_active_period (organization_id,farm_id,active_area_key,period_start,period_end,active_period_lock),
  CONSTRAINT fk_cost_settlements_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_settlements_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_settlements_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_settlements_run FOREIGN KEY (allocation_run_id) REFERENCES cost_allocation_runs(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_settlements_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_settlements_updated FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_settlements_verified FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_settlements_confirmed FOREIGN KEY (confirmed_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_cost_settlements_reversed FOREIGN KEY (reversed_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT ck_cost_settlement_profit CHECK (profit_amount=income_amount-cost_amount)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE cost_settlement_sources (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  settlement_id BIGINT UNSIGNED NOT NULL,
  direction ENUM('income','cost') NOT NULL,
  source_type VARCHAR(64) NOT NULL,
  source_id BIGINT UNSIGNED NULL,
  source_ref VARCHAR(128) NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  snapshot_json JSON NOT NULL,
  PRIMARY KEY (id),
  UNIQUE KEY uq_cost_settlement_source (settlement_id,direction,source_type,source_ref),
  CONSTRAINT fk_cost_settlement_source_settlement FOREIGN KEY (settlement_id) REFERENCES cost_settlements(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO permissions (code,name,module_code,description) VALUES
  ('cost.entry.confirm','确认成本台账','cost','确认核验后的成本并形成正式影响'),
  ('cost.asset.manage','管理成本资产','cost','登记、编辑、提交资产并计提折旧'),
  ('cost.asset.verify','核验成本资产','cost','独立核验资产及其凭据'),
  ('cost.asset.confirm','确认成本资产','cost','确认资产并允许计提折旧'),
  ('cost.settlement.manage','管理期间结算','cost','创建、编辑和提交期间结算'),
  ('cost.settlement.verify','核验期间结算','cost','独立核验期间结算快照'),
  ('cost.settlement.confirm','确认期间结算','cost','确认并锁定结算期间'),
  ('cost.settlement.reverse','执行反结算','cost','有痕解除已确认期间锁定')
ON DUPLICATE KEY UPDATE name=VALUES(name),description=VALUES(description);

INSERT IGNORE INTO role_permissions (role_id,permission_id)
SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
WHERE r.status='active' AND (
  (r.code='finance_staff' AND p.code IN ('cost.asset.manage','cost.asset.verify','cost.settlement.manage','cost.settlement.verify')) OR
  (r.code IN ('super_admin','breed_manager') AND p.code IN ('cost.entry.confirm','cost.asset.confirm','cost.settlement.confirm','cost.settlement.reverse'))
);

DROP TRIGGER IF EXISTS cost_entries_no_formal_update;
DROP TRIGGER IF EXISTS cost_entries_period_lock_insert;
DROP TRIGGER IF EXISTS cost_assets_no_formal_delete;
DROP TRIGGER IF EXISTS cost_assets_no_formal_update;
DROP TRIGGER IF EXISTS cost_depreciation_no_update;
DROP TRIGGER IF EXISTS cost_depreciation_no_delete;
DROP TRIGGER IF EXISTS cost_allocation_runs_no_update;
DROP TRIGGER IF EXISTS cost_allocation_runs_no_delete;
DROP TRIGGER IF EXISTS cost_allocation_details_no_update;
DROP TRIGGER IF EXISTS cost_allocation_details_no_delete;
DROP TRIGGER IF EXISTS cost_settlements_no_formal_update;
DROP TRIGGER IF EXISTS cost_settlements_no_formal_delete;
DROP TRIGGER IF EXISTS cost_settlement_sources_no_update;
DROP TRIGGER IF EXISTS cost_settlement_sources_no_delete;

DELIMITER $$
CREATE TRIGGER cost_entries_no_formal_update BEFORE UPDATE ON cost_entries FOR EACH ROW
BEGIN
  IF OLD.status IN ('verified','confirmed','reversed','void') AND (
    NOT(OLD.organization_id<=>NEW.organization_id) OR NOT(OLD.farm_id<=>NEW.farm_id) OR NOT(OLD.area_id<=>NEW.area_id) OR
    NOT(OLD.category_id<=>NEW.category_id) OR NOT(OLD.amount<=>NEW.amount) OR NOT(OLD.occurred_on<=>NEW.occurred_on) OR
    NOT(OLD.period_start<=>NEW.period_start) OR NOT(OLD.period_end<=>NEW.period_end) OR NOT(OLD.source_type<=>NEW.source_type) OR
    NOT(OLD.source_ref<=>NEW.source_ref) OR NOT(OLD.source_detail_json<=>NEW.source_detail_json) OR
    NOT(OLD.cost_nature<=>NEW.cost_nature) OR NOT(OLD.target_type<=>NEW.target_type) OR NOT(OLD.target_id<=>NEW.target_id) OR
    NOT(OLD.evidence_attachment_ids_json<=>NEW.evidence_attachment_ids_json) OR NOT(OLD.reversal_of_id<=>NEW.reversal_of_id)
  ) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='formal cost entry business fields are immutable'; END IF;
  IF OLD.status IN ('confirmed','reversed','void') AND OLD.status<>NEW.status THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='formal cost entry status is immutable';
  END IF;
  IF (NOT(OLD.occurred_on<=>NEW.occurred_on) OR NOT(OLD.amount<=>NEW.amount)) AND EXISTS(
    SELECT 1 FROM cost_settlements s WHERE s.organization_id=NEW.organization_id AND s.farm_id=NEW.farm_id
      AND s.status='confirmed' AND (s.area_id IS NULL OR s.area_id<=>NEW.area_id) AND NEW.occurred_on BETWEEN s.period_start AND s.period_end
  ) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='cost period is locked by confirmed settlement'; END IF;
  IF OLD.status<>NEW.status AND NEW.status='confirmed' AND EXISTS(
    SELECT 1 FROM cost_settlements s WHERE s.organization_id=NEW.organization_id AND s.farm_id=NEW.farm_id
      AND s.status='confirmed' AND (s.area_id IS NULL OR s.area_id<=>NEW.area_id) AND NEW.occurred_on BETWEEN s.period_start AND s.period_end
  ) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='cost period is locked by confirmed settlement'; END IF;
END$$

CREATE TRIGGER cost_entries_period_lock_insert BEFORE INSERT ON cost_entries FOR EACH ROW
BEGIN
  IF EXISTS(SELECT 1 FROM cost_settlements s WHERE s.organization_id=NEW.organization_id AND s.farm_id=NEW.farm_id
    AND s.status='confirmed' AND (s.area_id IS NULL OR s.area_id<=>NEW.area_id) AND NEW.occurred_on BETWEEN s.period_start AND s.period_end)
  THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='cost period is locked by confirmed settlement'; END IF;
END$$

CREATE TRIGGER cost_entries_no_formal_delete BEFORE DELETE ON cost_entries FOR EACH ROW
BEGIN IF OLD.status<>'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='only draft cost entries may be deleted'; END IF; END$$
CREATE TRIGGER cost_assets_no_formal_delete BEFORE DELETE ON cost_assets FOR EACH ROW
BEGIN IF OLD.status<>'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='only draft cost assets may be deleted'; END IF; END$$
CREATE TRIGGER cost_assets_no_formal_update BEFORE UPDATE ON cost_assets FOR EACH ROW
BEGIN IF OLD.status IN ('verified','confirmed','retired','disposed','cancelled') AND (
  NOT(OLD.organization_id<=>NEW.organization_id) OR NOT(OLD.farm_id<=>NEW.farm_id) OR NOT(OLD.area_id<=>NEW.area_id) OR
  NOT(OLD.code<=>NEW.code) OR NOT(OLD.name<=>NEW.name) OR NOT(OLD.asset_type<=>NEW.asset_type) OR
  NOT(OLD.category_id<=>NEW.category_id) OR NOT(OLD.purchase_date<=>NEW.purchase_date) OR
  NOT(OLD.original_value<=>NEW.original_value) OR NOT(OLD.salvage_value<=>NEW.salvage_value) OR
  NOT(OLD.useful_life_months<=>NEW.useful_life_months) OR NOT(OLD.depreciation_start_date<=>NEW.depreciation_start_date) OR
  NOT(OLD.allocation_driver<=>NEW.allocation_driver) OR NOT(OLD.target_type<=>NEW.target_type) OR
  NOT(OLD.target_id<=>NEW.target_id) OR NOT(OLD.note<=>NEW.note) OR
  NOT(OLD.evidence_attachment_ids_json<=>NEW.evidence_attachment_ids_json)
) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='formal cost asset business fields are immutable'; END IF; END$$
CREATE TRIGGER cost_depreciation_no_update BEFORE UPDATE ON cost_depreciation_entries FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='cost depreciation entries are immutable'$$
CREATE TRIGGER cost_depreciation_no_delete BEFORE DELETE ON cost_depreciation_entries FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='cost depreciation entries are immutable'$$
CREATE TRIGGER cost_allocation_runs_no_update BEFORE UPDATE ON cost_allocation_runs FOR EACH ROW
BEGIN IF NOT(OLD.organization_id<=>NEW.organization_id) OR NOT(OLD.farm_id<=>NEW.farm_id) OR NOT(OLD.area_id<=>NEW.area_id) OR NOT(OLD.period_start<=>NEW.period_start) OR NOT(OLD.period_end<=>NEW.period_end) OR NOT(OLD.rule_version_id<=>NEW.rule_version_id) OR NOT(OLD.source_total<=>NEW.source_total) OR NOT(OLD.allocated_total<=>NEW.allocated_total) OR NOT(OLD.participant_snapshot_json<=>NEW.participant_snapshot_json) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='cost allocation run snapshot is immutable'; END IF; END$$
CREATE TRIGGER cost_allocation_runs_no_delete BEFORE DELETE ON cost_allocation_runs FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='cost allocation runs are immutable'$$
CREATE TRIGGER cost_allocation_details_no_update BEFORE UPDATE ON cost_allocation_details FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='cost allocation details are immutable'$$
CREATE TRIGGER cost_allocation_details_no_delete BEFORE DELETE ON cost_allocation_details FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='cost allocation details are immutable'$$
CREATE TRIGGER cost_settlements_no_formal_update BEFORE UPDATE ON cost_settlements FOR EACH ROW
BEGIN IF OLD.status IN ('verified','confirmed','reversed','cancelled') AND (
  NOT(OLD.organization_id<=>NEW.organization_id) OR NOT(OLD.farm_id<=>NEW.farm_id) OR NOT(OLD.area_id<=>NEW.area_id) OR
  NOT(OLD.code<=>NEW.code) OR NOT(OLD.name<=>NEW.name) OR NOT(OLD.period_start<=>NEW.period_start) OR
  NOT(OLD.period_end<=>NEW.period_end) OR NOT(OLD.allocation_run_id<=>NEW.allocation_run_id) OR
  NOT(OLD.income_amount<=>NEW.income_amount) OR NOT(OLD.cost_amount<=>NEW.cost_amount) OR NOT(OLD.profit_amount<=>NEW.profit_amount)
) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='formal cost settlement business fields are immutable'; END IF; END$$
CREATE TRIGGER cost_settlements_no_formal_delete BEFORE DELETE ON cost_settlements FOR EACH ROW
BEGIN IF OLD.status<>'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='only draft cost settlements may be deleted'; END IF; END$$
CREATE TRIGGER cost_settlement_sources_no_update BEFORE UPDATE ON cost_settlement_sources FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='cost settlement sources are immutable'$$
CREATE TRIGGER cost_settlement_sources_no_delete BEFORE DELETE ON cost_settlement_sources FOR EACH ROW
BEGIN
  IF NOT EXISTS(SELECT 1 FROM cost_settlements s WHERE s.id=OLD.settlement_id AND s.status='draft')
  THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='formal cost settlement sources are immutable'; END IF;
END$$
DELIMITER ;
