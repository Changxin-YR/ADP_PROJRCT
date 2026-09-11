SET NAMES utf8mb4;

-- 请购单：把「库存预警 → 请购 → 采购单」这一段断链接通。
-- 一张请购单最多被转换成一张采购单（purchase_orders.requisition_id 唯一键双保险）。

CREATE TABLE IF NOT EXISTS purchase_requisitions (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  farm_id BIGINT UNSIGNED NOT NULL,
  area_id BIGINT UNSIGNED NULL,
  code VARCHAR(64) NOT NULL,
  name VARCHAR(120) NOT NULL,
  material_id BIGINT UNSIGNED NOT NULL,
  quantity DECIMAL(18,3) NOT NULL,
  warehouse_id BIGINT UNSIGNED NULL,
  reason VARCHAR(500) NOT NULL,
  alert_key VARCHAR(191) NULL,
  status ENUM('draft','submitted','approved','converted','cancelled') NOT NULL DEFAULT 'draft',
  cancellation_reason VARCHAR(500) NULL,
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  created_by BIGINT UNSIGNED NOT NULL,
  updated_by BIGINT UNSIGNED NULL,
  approved_by BIGINT UNSIGNED NULL,
  approved_at DATETIME NULL,
  converted_order_id BIGINT UNSIGNED NULL,
  converted_by BIGINT UNSIGNED NULL,
  converted_at DATETIME NULL,
  cancelled_by BIGINT UNSIGNED NULL,
  cancelled_at DATETIME NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_purchase_requisitions_org_code (organization_id,code),
  KEY idx_purchase_requisitions_material (material_id),
  KEY idx_purchase_requisitions_warehouse (warehouse_id),
  KEY idx_purchase_requisitions_scope_status (organization_id,farm_id,area_id,status),
  KEY idx_purchase_requisitions_alert_key (organization_id,alert_key),
  CONSTRAINT fk_purchase_requisitions_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_requisitions_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_requisitions_area FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_requisitions_material FOREIGN KEY (material_id) REFERENCES materials(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_requisitions_warehouse FOREIGN KEY (warehouse_id) REFERENCES warehouses(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_requisitions_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_requisitions_updated FOREIGN KEY (updated_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_requisitions_approved FOREIGN KEY (approved_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_requisitions_converted_by FOREIGN KEY (converted_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_requisitions_cancelled FOREIGN KEY (cancelled_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- 采购单回指请购来源：唯一键确保一张请购单只能转换出一张采购单。
DROP PROCEDURE IF EXISTS adp_migration_034_add_order_requisition;
DELIMITER $$
CREATE PROCEDURE adp_migration_034_add_order_requisition()
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'purchase_orders'
      AND COLUMN_NAME = 'requisition_id'
  ) THEN
    ALTER TABLE purchase_orders
      ADD COLUMN requisition_id BIGINT UNSIGNED NULL AFTER warehouse_id,
      ADD UNIQUE KEY uq_purchase_orders_requisition (requisition_id),
      ADD CONSTRAINT fk_purchase_orders_requisition FOREIGN KEY (requisition_id) REFERENCES purchase_requisitions(id) ON DELETE RESTRICT;
  END IF;
END$$
DELIMITER ;
CALL adp_migration_034_add_order_requisition();
DROP PROCEDURE IF EXISTS adp_migration_034_add_order_requisition;
