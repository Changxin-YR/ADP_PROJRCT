SET NAMES utf8mb4;

ALTER TABLE users
  MODIFY status ENUM('pending','rejected','active','disabled','must_change_password','retired') NOT NULL DEFAULT 'pending',
  ADD COLUMN retired_at DATETIME NULL,
  ADD COLUMN retired_by BIGINT UNSIGNED NULL,
  ADD KEY idx_users_retired_at (retired_at),
  ADD CONSTRAINT fk_users_retired_by FOREIGN KEY (retired_by) REFERENCES users(id) ON DELETE SET NULL;

ALTER TABLE audit_logs
  ADD COLUMN request_id CHAR(32) NULL,
  ADD COLUMN module_code VARCHAR(64) NULL,
  ADD COLUMN action_code VARCHAR(64) NULL,
  ADD COLUMN object_ref VARCHAR(128) NULL,
  ADD COLUMN actor_name_snapshot VARCHAR(100) NULL,
  ADD COLUMN actor_role_snapshot VARCHAR(255) NULL,
  ADD COLUMN reason VARCHAR(500) NULL,
  ADD COLUMN before_json JSON NULL,
  ADD COLUMN after_json JSON NULL,
  ADD COLUMN changed_fields_json JSON NULL,
  ADD COLUMN related_work_item_id BIGINT UNSIGNED NULL,
  ADD COLUMN correlation_id CHAR(32) NULL,
  ADD COLUMN retention_class VARCHAR(32) NOT NULL DEFAULT 'business',
  ADD KEY idx_audit_logs_request_id (request_id),
  ADD KEY idx_audit_logs_module_action_created (module_code, action_code, created_at);

CREATE TABLE work_items (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  assignee_user_id BIGINT UNSIGNED NULL,
  module_code VARCHAR(64) NOT NULL,
  action_code VARCHAR(64) NOT NULL,
  object_type VARCHAR(64) NOT NULL,
  object_id BIGINT UNSIGNED NULL,
  object_ref VARCHAR(128) NULL,
  source_key VARCHAR(191) NOT NULL,
  title VARCHAR(255) NOT NULL,
  detail VARCHAR(1000) NULL,
  priority ENUM('low','normal','high','critical') NOT NULL DEFAULT 'normal',
  status ENUM('pending','claimed','in_progress','completed','cancelled','escalated') NOT NULL DEFAULT 'pending',
  due_at DATETIME NULL,
  claimed_by BIGINT UNSIGNED NULL,
  claimed_at DATETIME NULL,
  completed_by BIGINT UNSIGNED NULL,
  completed_at DATETIME NULL,
  completion_note VARCHAR(500) NULL,
  cancelled_by BIGINT UNSIGNED NULL,
  cancelled_at DATETIME NULL,
  cancel_reason VARCHAR(500) NULL,
  row_version INT UNSIGNED NOT NULL DEFAULT 1,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_work_items_source_key (source_key),
  KEY idx_work_items_assignee_status_due (assignee_user_id, status, due_at),
  KEY idx_work_items_object (object_type, object_id),
  CONSTRAINT fk_work_items_assignee FOREIGN KEY (assignee_user_id) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_work_items_claimed_by FOREIGN KEY (claimed_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_work_items_completed_by FOREIGN KEY (completed_by) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_work_items_cancelled_by FOREIGN KEY (cancelled_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE notifications (
  id BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  recipient_user_id BIGINT UNSIGNED NOT NULL,
  module_code VARCHAR(64) NOT NULL,
  notification_type VARCHAR(64) NOT NULL,
  object_type VARCHAR(64) NULL,
  object_id BIGINT UNSIGNED NULL,
  object_ref VARCHAR(128) NULL,
  dedup_key VARCHAR(191) NOT NULL,
  title VARCHAR(255) NOT NULL,
  body VARCHAR(1000) NULL,
  level ENUM('low','normal','high','critical') NOT NULL DEFAULT 'normal',
  status ENUM('unread','read','closed','escalated') NOT NULL DEFAULT 'unread',
  occurrence_count INT UNSIGNED NOT NULL DEFAULT 1,
  first_occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  last_occurred_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  read_at DATETIME NULL,
  closed_by BIGINT UNSIGNED NULL,
  closed_at DATETIME NULL,
  close_conclusion VARCHAR(500) NULL,
  created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
  updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
  PRIMARY KEY (id),
  UNIQUE KEY uq_notifications_recipient_dedup (recipient_user_id, dedup_key),
  KEY idx_notifications_recipient_status_last (recipient_user_id, status, last_occurred_at),
  CONSTRAINT fk_notifications_recipient FOREIGN KEY (recipient_user_id) REFERENCES users(id) ON DELETE RESTRICT,
  CONSTRAINT fk_notifications_closed_by FOREIGN KEY (closed_by) REFERENCES users(id) ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

ALTER TABLE audit_logs
  ADD CONSTRAINT fk_audit_logs_work_item
  FOREIGN KEY (related_work_item_id) REFERENCES work_items(id) ON DELETE SET NULL;

CREATE TRIGGER audit_logs_no_update
BEFORE UPDATE ON audit_logs
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit_logs is append-only';

CREATE TRIGGER audit_logs_no_delete
BEFORE DELETE ON audit_logs
FOR EACH ROW
SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'audit_logs is append-only';

INSERT INTO permissions (code, name, module_code, description) VALUES
  ('audit.view', '查看操作日志', 'admin', '查询业务、安全和权限操作审计记录'),
  ('work_item.view', '查看待办与消息', 'workbench', '查看当前用户可见的待办、消息和完成历史'),
  ('work_item.manage', '处理待办与消息', 'workbench', '认领、完成、取消和关闭授权范围内的待办与消息')
ON DUPLICATE KEY UPDATE
  name = VALUES(name), module_code = VALUES(module_code), description = VALUES(description);

INSERT IGNORE INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles AS r
CROSS JOIN permissions AS p
WHERE r.status = 'active'
  AND (
    (p.code IN ('audit.view', 'work_item.view', 'work_item.manage')
      AND r.code IN ('super_admin', 'breed_manager'))
    OR (p.code = 'work_item.view'
      AND r.code IN ('breed_worker', 'warehouse_manager', 'purchaser', 'finance_staff', 'sales_staff'))
  );
