SET NAMES utf8mb4;

CREATE TABLE IF NOT EXISTS accounting_periods (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  farm_id BIGINT UNSIGNED NOT NULL,
  period_start DATE NOT NULL,
  period_end DATE NOT NULL,
  status ENUM('open','closed') NOT NULL DEFAULT 'open',
  created_by BIGINT UNSIGNED NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_accounting_period_scope_start (organization_id,farm_id,period_start),
  KEY idx_accounting_period_open (organization_id,farm_id,status,period_start),
  CONSTRAINT fk_accounting_period_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_accounting_period_farm FOREIGN KEY (farm_id) REFERENCES farms(id) ON DELETE RESTRICT,
  CONSTRAINT fk_accounting_period_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT ck_accounting_period_dates CHECK (period_start <= period_end)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Initialize the current calendar month so existing installations remain usable.
INSERT IGNORE INTO accounting_periods (organization_id,farm_id,period_start,period_end,status)
SELECT f.organization_id,f.id,DATE_FORMAT(CURRENT_DATE(),'%Y-%m-01'),LAST_DAY(CURRENT_DATE()),'open'
FROM farms f WHERE f.status IN ('active','verified');

DROP TRIGGER IF EXISTS farms_accounting_period_default;
DELIMITER $$
CREATE TRIGGER farms_accounting_period_default AFTER INSERT ON farms FOR EACH ROW
BEGIN
  IF NEW.status IN ('active','verified') THEN
    INSERT IGNORE INTO accounting_periods (organization_id,farm_id,period_start,period_end,status)
    VALUES (NEW.organization_id,NEW.id,DATE_FORMAT(CURRENT_DATE(),'%Y-%m-01'),LAST_DAY(CURRENT_DATE()),'open');
  END IF;
END$$
DELIMITER ;
