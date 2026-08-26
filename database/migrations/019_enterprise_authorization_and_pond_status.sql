SET NAMES utf8mb4;

INSERT INTO permissions (code,name,module_code,description) VALUES
  ('auth.role.manage','管理角色权限','admin','仅超级管理员可定义或复制角色权限')
ON DUPLICATE KEY UPDATE
  name=VALUES(name),module_code=VALUES(module_code),description=VALUES(description);

INSERT IGNORE INTO role_permissions (role_id,permission_id)
SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
WHERE r.code='super_admin' AND p.code='auth.role.manage';

DELETE rp FROM role_permissions rp
INNER JOIN roles r ON r.id=rp.role_id
INNER JOIN permissions p ON p.id=rp.permission_id
WHERE p.code IN ('auth.review','auth.user.manage','audit.view') AND r.code<>'super_admin';

INSERT IGNORE INTO role_permissions (role_id,permission_id)
SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
WHERE (r.code='purchaser' AND p.code='finance.payable.view')
   OR (r.code='sales_staff' AND p.code='finance.receivable.view');

CREATE TABLE pond_status_change_requests (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  organization_id BIGINT UNSIGNED NOT NULL,
  pond_id BIGINT UNSIGNED NOT NULL,
  from_status ENUM('build','stocked','farming','rest','clean','rebuild') NOT NULL,
  to_status ENUM('build','stocked','farming','rest','clean','rebuild') NOT NULL,
  reason VARCHAR(500) NOT NULL,
  status ENUM('submitted','verified') NOT NULL DEFAULT 'submitted',
  pond_version INT UNSIGNED NOT NULL,
  requested_by BIGINT UNSIGNED NOT NULL,
  requested_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  verified_by BIGINT UNSIGNED NULL,
  verified_at DATETIME NULL,
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  active_pond_id BIGINT UNSIGNED GENERATED ALWAYS AS (CASE WHEN status='submitted' THEN pond_id ELSE NULL END) STORED,
  PRIMARY KEY (id),
  UNIQUE KEY uq_pond_status_active_request (active_pond_id),
  KEY idx_pond_status_history (pond_id,requested_at),
  CONSTRAINT chk_pond_status_transition CHECK (
    (from_status='build' AND to_status='stocked') OR
    (from_status='stocked' AND to_status='farming') OR
    (from_status='farming' AND to_status IN ('rest','clean')) OR
    (from_status='rest' AND to_status IN ('stocked','rebuild')) OR
    (from_status='clean' AND to_status IN ('rest','rebuild')) OR
    (from_status='rebuild' AND to_status='build')
  ),
  CONSTRAINT fk_pond_status_org FOREIGN KEY (organization_id) REFERENCES organizations(id) ON DELETE RESTRICT,
  CONSTRAINT fk_pond_status_pond FOREIGN KEY (pond_id) REFERENCES ponds(id) ON DELETE RESTRICT,
  CONSTRAINT fk_pond_status_requested_by FOREIGN KEY (requested_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_pond_status_verified_by FOREIGN KEY (verified_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DELIMITER $$
CREATE TRIGGER pond_status_requests_no_formal_update BEFORE UPDATE ON pond_status_change_requests FOR EACH ROW
BEGIN IF OLD.status='verified' THEN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='verified pond status request is immutable'; END IF; END$$
CREATE TRIGGER pond_status_requests_no_delete BEFORE DELETE ON pond_status_change_requests FOR EACH ROW
BEGIN SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT='pond status request cannot be deleted'; END$$
DELIMITER ;
