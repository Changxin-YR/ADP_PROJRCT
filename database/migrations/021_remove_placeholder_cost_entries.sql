SET NAMES utf8mb4;

DROP TRIGGER IF EXISTS cost_entries_no_formal_delete;

DELETE FROM cost_entries
WHERE source_type = 'legacy_import'
  AND source_ref = 'LEGACY-INIT-2026'
  AND created_by IS NULL
  AND updated_by IS NULL
  AND verified_by IS NULL
  AND confirmed_by IS NULL;

DELIMITER $$
CREATE TRIGGER cost_entries_no_formal_delete BEFORE DELETE ON cost_entries FOR EACH ROW
BEGIN IF OLD.status<>'draft' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='only draft cost entries may be deleted'; END IF; END$$
DELIMITER ;
