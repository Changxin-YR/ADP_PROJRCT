SET NAMES utf8mb4;

DROP TEMPORARY TABLE IF EXISTS sales_harvest_roots_preflight;
CREATE TEMPORARY TABLE sales_harvest_roots_preflight (
  sales_delivery_id BIGINT UNSIGNED NOT NULL,
  harvest_root_id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (sales_delivery_id)
);

INSERT INTO sales_harvest_roots_preflight (sales_delivery_id,harvest_root_id)
WITH RECURSIVE harvest_lineage (sales_delivery_id,harvest_id,parent_id) AS (
  SELECT d.id,p.id,p.correction_of_id
  FROM sales_deliveries d JOIN production_documents p ON p.id=d.harvest_document_id
  UNION ALL
  SELECT lineage.sales_delivery_id,p.id,p.correction_of_id
  FROM harvest_lineage lineage JOIN production_documents p ON p.id=lineage.parent_id
)
SELECT sales_delivery_id,harvest_id FROM harvest_lineage WHERE parent_id IS NULL;

DROP TEMPORARY TABLE IF EXISTS sales_harvest_parent_roots_preflight;
CREATE TEMPORARY TABLE sales_harvest_parent_roots_preflight LIKE sales_harvest_roots_preflight;
INSERT INTO sales_harvest_parent_roots_preflight
SELECT sales_delivery_id,harvest_root_id FROM sales_harvest_roots_preflight;

DROP TEMPORARY TABLE IF EXISTS sales_harvest_corrections_preflight;
CREATE TEMPORARY TABLE sales_harvest_corrections_preflight (
  singleton TINYINT UNSIGNED NOT NULL,
  PRIMARY KEY (singleton)
);
INSERT INTO sales_harvest_corrections_preflight (singleton) VALUES (1);
INSERT INTO sales_harvest_corrections_preflight (singleton)
SELECT 1
FROM sales_deliveries correction
JOIN sales_harvest_roots_preflight child_root ON child_root.sales_delivery_id=correction.id
JOIN sales_harvest_parent_roots_preflight parent_root ON parent_root.sales_delivery_id=correction.correction_of_id
WHERE correction.correction_of_id IS NOT NULL
  AND child_root.harvest_root_id<>parent_root.harvest_root_id
LIMIT 1;
DROP TEMPORARY TABLE sales_harvest_corrections_preflight;
DROP TEMPORARY TABLE sales_harvest_parent_roots_preflight;

DROP TEMPORARY TABLE IF EXISTS sales_harvest_claims_preflight;
CREATE TEMPORARY TABLE sales_harvest_claims_preflight (
  harvest_root_id BIGINT UNSIGNED NOT NULL,
  sales_delivery_id BIGINT UNSIGNED NOT NULL,
  PRIMARY KEY (harvest_root_id),
  UNIQUE KEY uq_sales_harvest_claim_delivery (sales_delivery_id)
);

INSERT INTO sales_harvest_claims_preflight (harvest_root_id,sales_delivery_id)
SELECT roots.harvest_root_id,roots.sales_delivery_id
FROM sales_harvest_roots_preflight roots
JOIN sales_deliveries delivery ON delivery.id=roots.sales_delivery_id
WHERE delivery.correction_of_id IS NULL;

ALTER TABLE sales_deliveries
  ADD COLUMN harvest_root_id BIGINT UNSIGNED NULL AFTER harvest_document_id,
  ADD KEY idx_sales_deliveries_harvest_root (harvest_root_id),
  ADD CONSTRAINT fk_sales_deliveries_harvest_root FOREIGN KEY (harvest_root_id)
    REFERENCES production_documents(id) ON DELETE RESTRICT;

DROP TRIGGER IF EXISTS sales_deliveries_no_verified_update;
DELIMITER $$
CREATE TRIGGER sales_deliveries_no_verified_update BEFORE UPDATE ON sales_deliveries FOR EACH ROW
BEGIN
  IF OLD.status='verified' AND COALESCE(@adp_sales_hardening_backfill,0)<>1 THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='verified sales delivery is immutable';
  END IF;
END$$
DELIMITER ;

SET @adp_sales_hardening_backfill=1;
UPDATE sales_deliveries delivery
JOIN sales_harvest_roots_preflight roots ON roots.sales_delivery_id=delivery.id
SET delivery.harvest_root_id=roots.harvest_root_id;
SET @adp_sales_hardening_backfill=0;

DROP TRIGGER sales_deliveries_no_verified_update;
DELIMITER $$
CREATE TRIGGER sales_deliveries_no_verified_update BEFORE UPDATE ON sales_deliveries FOR EACH ROW
BEGIN
  IF OLD.status='verified' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='verified sales delivery is immutable';
  END IF;
END$$
DELIMITER ;

ALTER TABLE sales_deliveries MODIFY harvest_root_id BIGINT UNSIGNED NOT NULL;

CREATE TABLE sales_delivery_harvest_claims (
  harvest_root_id BIGINT UNSIGNED NOT NULL,
  sales_delivery_id BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (harvest_root_id),
  UNIQUE KEY uq_sales_deliveries_harvest_root (sales_delivery_id),
  CONSTRAINT fk_sales_harvest_claim_root FOREIGN KEY (harvest_root_id)
    REFERENCES production_documents(id) ON DELETE RESTRICT,
  CONSTRAINT fk_sales_harvest_claim_delivery FOREIGN KEY (sales_delivery_id)
    REFERENCES sales_deliveries(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO sales_delivery_harvest_claims (harvest_root_id,sales_delivery_id)
SELECT harvest_root_id,sales_delivery_id FROM sales_harvest_claims_preflight;

DROP TEMPORARY TABLE sales_harvest_claims_preflight;
DROP TEMPORARY TABLE sales_harvest_roots_preflight;

DROP TRIGGER IF EXISTS sales_orders_no_approved_business_update;
DELIMITER $$
CREATE TRIGGER sales_orders_no_approved_business_update BEFORE UPDATE ON sales_orders FOR EACH ROW
BEGIN
  IF OLD.status IN ('approved','partially_delivered','fully_delivered','closed','cancelled','disputed') AND (
    NOT (OLD.organization_id<=>NEW.organization_id) OR NOT (OLD.farm_id<=>NEW.farm_id) OR
    NOT (OLD.area_id<=>NEW.area_id) OR NOT (OLD.pond_id<=>NEW.pond_id) OR
    NOT (OLD.batch_id<=>NEW.batch_id) OR NOT (OLD.customer_id<=>NEW.customer_id) OR
    NOT (OLD.code<=>NEW.code) OR NOT (OLD.name<=>NEW.name) OR
    NOT (OLD.species<=>NEW.species) OR NOT (OLD.quantity<=>NEW.quantity) OR
    NOT (OLD.unit<=>NEW.unit) OR NOT (OLD.unit_price<=>NEW.unit_price) OR
    NOT (OLD.total_amount<=>NEW.total_amount) OR NOT (OLD.sold_at<=>NEW.sold_at) OR
    NOT (OLD.due_date<=>NEW.due_date) OR NOT (OLD.note<=>NEW.note) OR
    NOT (OLD.evidence_attachment_ids_json<=>NEW.evidence_attachment_ids_json)
  ) THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='approved sales order business fields are immutable';
  END IF;
END$$
DELIMITER ;
