SET NAMES utf8mb4;

ALTER TABLE purchase_payables
  MODIFY COLUMN status ENUM('unpaid','partial','settled','overpaid','disputed','cancelled') NOT NULL DEFAULT 'unpaid';

ALTER TABLE purchase_payments
  ADD COLUMN payment_method VARCHAR(32) NULL AFTER paid_at;

UPDATE purchase_payments SET payment_method='other' WHERE payment_method IS NULL OR payment_method='';

ALTER TABLE purchase_payments
  MODIFY COLUMN payment_method VARCHAR(32) NOT NULL;

CREATE TABLE purchase_payable_adjustments (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  payable_id BIGINT UNSIGNED NOT NULL,
  source_receipt_id BIGINT UNSIGNED NOT NULL,
  amount_delta DECIMAL(18,2) NOT NULL,
  reason VARCHAR(500) NOT NULL,
  created_by BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_purchase_payable_adjustments_receipt (source_receipt_id),
  KEY idx_purchase_payable_adjustments_payable (payable_id,created_at),
  CONSTRAINT fk_purchase_payable_adjustments_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_payable_adjustments_payable FOREIGN KEY (payable_id) REFERENCES purchase_payables(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_payable_adjustments_receipt FOREIGN KEY (source_receipt_id) REFERENCES warehouse_documents(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_payable_adjustments_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE purchase_payment_reversals (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  payment_id BIGINT UNSIGNED NOT NULL,
  amount DECIMAL(18,2) NOT NULL,
  reversal_reason VARCHAR(500) NOT NULL,
  evidence_attachment_ids_json JSON NOT NULL,
  created_by BIGINT UNSIGNED NOT NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_purchase_payment_reversals_payment (payment_id),
  CONSTRAINT fk_purchase_payment_reversals_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_payment_reversals_payment FOREIGN KEY (payment_id) REFERENCES purchase_payments(id) ON DELETE RESTRICT,
  CONSTRAINT fk_purchase_payment_reversals_created FOREIGN KEY (created_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DELIMITER $$
CREATE TRIGGER purchase_payable_adjustments_no_update BEFORE UPDATE ON purchase_payable_adjustments FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='purchase payable adjustment is append-only'$$
CREATE TRIGGER purchase_payable_adjustments_no_delete BEFORE DELETE ON purchase_payable_adjustments FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='purchase payable adjustment is append-only'$$
CREATE TRIGGER purchase_payment_reversals_no_update BEFORE UPDATE ON purchase_payment_reversals FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='purchase payment reversal is append-only'$$
CREATE TRIGGER purchase_payment_reversals_no_delete BEFORE DELETE ON purchase_payment_reversals FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='purchase payment reversal is append-only'$$
DELIMITER ;
