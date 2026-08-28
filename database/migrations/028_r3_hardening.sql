SET NAMES utf8mb4;

-- Bind non-admin data scopes to a tenant hierarchy. Legacy global rows remain
-- usable only by super_admin until an administrator grants a bound scope.
DROP PROCEDURE IF EXISTS adp_migration_028_scope_columns;
DELIMITER $$
CREATE PROCEDURE adp_migration_028_scope_columns()
BEGIN
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='data_scopes' AND COLUMN_NAME='organization_id') THEN
    ALTER TABLE data_scopes ADD COLUMN organization_id BIGINT UNSIGNED NULL AFTER name;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM information_schema.COLUMNS WHERE TABLE_SCHEMA=DATABASE() AND TABLE_NAME='data_scopes' AND COLUMN_NAME='farm_id') THEN
    ALTER TABLE data_scopes ADD COLUMN farm_id BIGINT UNSIGNED NULL AFTER organization_id;
  END IF;
END$$
DELIMITER ;
CALL adp_migration_028_scope_columns();
DROP PROCEDURE IF EXISTS adp_migration_028_scope_columns;

UPDATE data_scopes ds
JOIN areas a ON a.id=ds.area_id
SET ds.organization_id=a.organization_id, ds.farm_id=a.farm_id
WHERE ds.scope_type='area' AND (ds.organization_id IS NULL OR ds.farm_id IS NULL);

INSERT INTO data_scopes (code, name, scope_type, organization_id, farm_id, area_id, status)
SELECT CONCAT('org-', o.id, '-all'), CONCAT(o.name, '全企业数据'), 'farm', o.id, NULL, NULL, 'active'
FROM organizations o
WHERE o.status='active'
  AND NOT EXISTS (SELECT 1 FROM data_scopes ds WHERE ds.code=CONCAT('org-', o.id, '-all'));

INSERT INTO data_scopes (code, name, scope_type, organization_id, farm_id, area_id, status)
SELECT CONCAT('farm-', f.id, '-all'), CONCAT(f.name, '全场数据'), 'farm', f.organization_id, f.id, NULL, 'active'
FROM farms f
WHERE f.status IN ('active', 'verified')
  AND NOT EXISTS (SELECT 1 FROM data_scopes ds WHERE ds.code=CONCAT('farm-', f.id, '-all'));

ALTER TABLE data_scopes
  ADD KEY idx_data_scopes_org_farm (organization_id,farm_id),
  ADD CONSTRAINT fk_data_scopes_organization FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  ADD CONSTRAINT fk_data_scopes_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT;

DROP TRIGGER IF EXISTS sales_deliveries_no_confirmed_settlement_insert;
DROP TRIGGER IF EXISTS sales_deliveries_no_confirmed_settlement_update;
DELIMITER $$
CREATE TRIGGER sales_deliveries_no_confirmed_settlement_insert BEFORE INSERT ON sales_deliveries FOR EACH ROW
BEGIN
  IF NEW.status='verified' AND EXISTS (
    SELECT 1 FROM sales_orders o JOIN cost_settlements s
      ON s.organization_id=o.organization_id AND s.farm_id=o.farm_id
     AND (s.area_id IS NULL OR o.area_id IS NULL OR s.area_id=o.area_id)
    WHERE o.id=NEW.sales_order_id AND s.status='confirmed'
      AND DATE(NEW.delivered_at) BETWEEN s.period_start AND s.period_end
  ) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='confirmed settlement period is immutable'; END IF;
END$$
CREATE TRIGGER sales_deliveries_no_confirmed_settlement_update BEFORE UPDATE ON sales_deliveries FOR EACH ROW
BEGIN
  IF NEW.status='verified' AND (OLD.status<>'verified' OR NOT (OLD.delivered_at<=>NEW.delivered_at)) AND EXISTS (
    SELECT 1 FROM sales_orders o JOIN cost_settlements s
      ON s.organization_id=o.organization_id AND s.farm_id=o.farm_id
     AND (s.area_id IS NULL OR o.area_id IS NULL OR s.area_id=o.area_id)
    WHERE o.id=NEW.sales_order_id AND s.status='confirmed'
      AND DATE(NEW.delivered_at) BETWEEN s.period_start AND s.period_end
  ) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='confirmed settlement period is immutable'; END IF;
END$$
DELIMITER ;
