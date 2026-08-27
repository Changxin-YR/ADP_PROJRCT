SET NAMES utf8mb4;

DROP PROCEDURE IF EXISTS adp_migration_026_add_warehouse_row_version;
DELIMITER $$
CREATE PROCEDURE adp_migration_026_add_warehouse_row_version()
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'warehouses'
      AND COLUMN_NAME = 'row_version'
  ) THEN
    ALTER TABLE warehouses
      ADD COLUMN row_version INT UNSIGNED NOT NULL DEFAULT 1 AFTER status;
  END IF;
END$$
DELIMITER ;
CALL adp_migration_026_add_warehouse_row_version();
DROP PROCEDURE IF EXISTS adp_migration_026_add_warehouse_row_version;

DELIMITER $$
CREATE TRIGGER sales_deliveries_no_confirmed_settlement_insert BEFORE INSERT ON sales_deliveries FOR EACH ROW
BEGIN
  IF NEW.status='verified' AND EXISTS (
    SELECT 1 FROM sales_orders o JOIN cost_settlements s ON s.organization_id=o.organization_id AND s.farm_id=o.farm_id AND s.area_id<=>o.area_id
    WHERE o.id=NEW.sales_order_id AND s.status='confirmed' AND DATE(NEW.delivered_at) BETWEEN s.period_start AND s.period_end
  ) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='confirmed settlement period is immutable'; END IF;
END$$
CREATE TRIGGER sales_deliveries_no_confirmed_settlement_update BEFORE UPDATE ON sales_deliveries FOR EACH ROW
BEGIN
  IF NEW.status='verified' AND (OLD.status<>'verified' OR NOT (OLD.delivered_at<=>NEW.delivered_at)) AND EXISTS (
    SELECT 1 FROM sales_orders o JOIN cost_settlements s ON s.organization_id=o.organization_id AND s.farm_id=o.farm_id AND s.area_id<=>o.area_id
    WHERE o.id=NEW.sales_order_id AND s.status='confirmed' AND DATE(NEW.delivered_at) BETWEEN s.period_start AND s.period_end
  ) THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='confirmed settlement period is immutable'; END IF;
END$$
DELIMITER ;
