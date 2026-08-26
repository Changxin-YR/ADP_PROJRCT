SET NAMES utf8mb4;

-- confirmed/void entries are immutable. Corrections use a linked negative reversal row.
DROP TRIGGER IF EXISTS cost_entries_no_posted_update;
DROP TRIGGER IF EXISTS cost_entries_no_formal_delete;

DELIMITER $$

CREATE TRIGGER cost_entries_no_posted_update
BEFORE UPDATE ON cost_entries
FOR EACH ROW
BEGIN
  IF OLD.status IN ('confirmed', 'void') THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'confirmed cost entries are immutable; create a reversal instead';
  END IF;
END$$

CREATE TRIGGER cost_entries_no_formal_delete
BEFORE DELETE ON cost_entries
FOR EACH ROW
BEGIN
  IF OLD.status <> 'draft' THEN
    SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'only draft cost entries may be deleted';
  END IF;
END$$

DELIMITER ;

INSERT INTO permissions (code, name, module_code, description) VALUES
  ('cost.entry.manage', '录入与提交成本', 'cost', '创建草稿、编辑草稿、提交核验和删除未正式录入草稿'),
  ('cost.entry.verify', '核验成本台账', 'cost', '核验待核验成本并生成不可编辑的正式台账'),
  ('cost.entry.reverse', '冲销成本台账', 'cost', '对已核验成本创建关联冲销记录')
ON DUPLICATE KEY UPDATE
  name = VALUES(name), module_code = VALUES(module_code), description = VALUES(description);

INSERT IGNORE INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles AS r
CROSS JOIN permissions AS p
WHERE r.status = 'active'
  AND (
    (p.code IN ('cost.entry.manage', 'cost.entry.verify', 'cost.entry.reverse')
      AND r.code IN ('super_admin', 'finance_staff'))
    OR (p.code IN ('cost.entry.manage', 'cost.entry.verify')
      AND r.code = 'breed_manager')
  );
