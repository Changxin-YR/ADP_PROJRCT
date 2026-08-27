SET NAMES utf8mb4;

ALTER TABLE warehouse_alert_actions
  ADD COLUMN resolution_reference_type VARCHAR(32) NULL AFTER resolution_note,
  ADD COLUMN resolution_reference_id BIGINT UNSIGNED NULL AFTER resolution_reference_type,
  ADD KEY idx_warehouse_alert_actions_reference (resolution_reference_type, resolution_reference_id);
