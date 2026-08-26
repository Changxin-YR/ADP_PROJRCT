-- 002_roles_and_scopes_expansion.sql
-- 对齐功能文档：7 种角色（超级管理员/养殖管理员/养殖作业员/仓储管理员/采购人员/财务人员/销售人员）
-- 数据范围扩展为三级：farm=全场 / area=区域 / personal=仅本人
SET NAMES utf8mb4;

-- 1) data_scopes.scope_type 扩展为三级，area_id 允许为空（全场/个人范围不绑定区域）
ALTER TABLE data_scopes
  MODIFY COLUMN scope_type ENUM('farm', 'area', 'personal') NOT NULL,
  MODIFY COLUMN area_id BIGINT UNSIGNED NULL;

-- 2) registration_applications 增加申请数据范围字段（幂等）
DROP PROCEDURE IF EXISTS adp_migration_002_add_scope;
DELIMITER $$
CREATE PROCEDURE adp_migration_002_add_scope()
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM information_schema.COLUMNS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'registration_applications'
      AND COLUMN_NAME = 'desired_scope_type'
  ) THEN
    ALTER TABLE registration_applications
      ADD COLUMN desired_scope_type ENUM('farm', 'area', 'personal') NULL AFTER area_id;
  END IF;
END$$
DELIMITER ;
CALL adp_migration_002_add_scope();
DROP PROCEDURE IF EXISTS adp_migration_002_add_scope;

-- 3) 角色字典对齐功能文档：7 种在用角色；历史角色 area_manager/farmer 停用
INSERT INTO roles (code, name, status, description)
VALUES
  ('super_admin',      '超级管理员', 'active', '平台级账号管理、审核与系统配置'),
  ('breed_manager',    '养殖管理员', 'active', '全场/区域养殖生产管理，具备审核与账号管理权限'),
  ('breed_worker',     '养殖作业员', 'active', '执行投喂、巡塘、水质检测等日常作业'),
  ('warehouse_manager','仓储管理员', 'active', '饲料、药品、物资出入库与库存管理'),
  ('purchaser',        '采购人员',   'active', '采购订单、供应商与应付账款管理'),
  ('finance_staff',    '财务人员',   'active', '费用审核、成本核算与资金管理'),
  ('sales_staff',      '销售人员',   'active', '销售订单、客户与应收账款管理'),
  ('area_manager',     '区域管理员', 'disabled', '历史角色：已由养殖管理员替代'),
  ('farmer',           '养殖员',     'disabled', '历史角色：已由养殖作业员替代')
ON DUPLICATE KEY UPDATE
  name = VALUES(name),
  status = VALUES(status),
  description = VALUES(description),
  updated_at = CURRENT_TIMESTAMP;

-- 4) 数据范围字典：全场 / 区域 / 个人 三级
INSERT INTO data_scopes (code, name, scope_type, area_id, status)
SELECT 'farm-all', '全场数据（所有基地）', 'farm', NULL, 'active'
WHERE NOT EXISTS (SELECT 1 FROM data_scopes WHERE code = 'farm-all');

INSERT INTO data_scopes (code, name, scope_type, area_id, status)
SELECT 'personal-self', '仅本人数据', 'personal', NULL, 'active'
WHERE NOT EXISTS (SELECT 1 FROM data_scopes WHERE code = 'personal-self');

INSERT INTO data_scopes (code, name, scope_type, area_id, status)
SELECT CONCAT(a.code, '-all'), CONCAT(a.name, '全部数据'), 'area', a.id, 'active'
FROM areas AS a
WHERE NOT EXISTS (
  SELECT 1 FROM data_scopes AS existing WHERE existing.code = CONCAT(a.code, '-all')
);

-- 5) 角色权限：管理员角色具备审核/账号管理；业务角色进入工作台
INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles AS r
JOIN permissions AS p
  ON (
    (r.code = 'super_admin' AND p.code IN ('auth.review', 'auth.user.manage', 'auth.session.view', 'workbench.enter'))
    OR (r.code = 'breed_manager' AND p.code IN ('auth.review', 'auth.user.manage', 'workbench.enter'))
    OR (r.code IN ('breed_worker', 'warehouse_manager', 'purchaser', 'finance_staff', 'sales_staff')
        AND p.code = 'workbench.enter')
  )
LEFT JOIN role_permissions AS existing
  ON existing.role_id = r.id
 AND existing.permission_id = p.id
WHERE existing.role_id IS NULL
  AND r.status = 'active';
