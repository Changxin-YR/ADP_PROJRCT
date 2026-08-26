SET NAMES utf8mb4;
SET character_set_client = utf8mb4;
SET character_set_connection = utf8mb4;
SET character_set_results = utf8mb4;

-- 生产环境只初始化角色、权限、基地和数据范围字典，不创建任何账号。
-- 角色字典对齐功能文档：7 种在用角色；历史角色停用
INSERT INTO roles (code, name, status, description)
VALUES
  ('super_admin',      '超级管理员', 'active', '平台级账号管理、审核与系统配置'),
  ('breed_manager',    '养殖管理员', 'active', '全场/区域养殖生产管理与业务审核'),
  ('breed_worker',     '养殖作业员', 'active', '执行投喂、巡塘、水质检测等日常作业'),
  ('warehouse_manager','仓储管理员', 'active', '饲料、药品、物资出入库与库存管理'),
  ('purchaser',        '采购人员',   'active', '采购订单、供应商与应付账款管理'),
  ('finance_staff',    '财务人员',   'active', '费用审核、成本核算与资金管理'),
  ('sales_staff',      '销售人员',   'active', '销售订单、客户与应收账款管理'),
  ('area_manager',     '区域管理员', 'disabled', '历史角色：已由养殖管理员替代'),
  ('farmer',           '养殖员',     'disabled', '历史角色：已由养殖作业员替代')
ON DUPLICATE KEY UPDATE
  name = VALUES(name), status = VALUES(status), description = VALUES(description), updated_at = CURRENT_TIMESTAMP;

INSERT INTO permissions (code, name, module_code, description)
VALUES
  ('auth.review', '审核注册申请', 'auth', '允许查看并审核公开注册申请'),
  ('auth.user.manage', '管理认证账号', 'auth', '允许启用、停用、重置密码和分配角色'),
  ('auth.session.view', '查看会话概览', 'auth', '允许查看账号会话和安全状态'),
  ('workbench.enter', '进入工作台', 'workbench', '允许进入后续业务工作区')
ON DUPLICATE KEY UPDATE
  name = VALUES(name), module_code = VALUES(module_code), description = VALUES(description), updated_at = CURRENT_TIMESTAMP;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles AS r
JOIN permissions AS p ON (
  (r.code = 'super_admin' AND p.code IN ('auth.review', 'auth.user.manage', 'auth.session.view', 'auth.role.manage', 'workbench.enter'))
  OR (r.code = 'breed_manager' AND p.code = 'workbench.enter')
  OR (r.code IN ('breed_worker', 'warehouse_manager', 'purchaser', 'finance_staff', 'sales_staff')
      AND p.code = 'workbench.enter')
)
LEFT JOIN role_permissions AS existing ON existing.role_id = r.id AND existing.permission_id = p.id
WHERE existing.role_id IS NULL
  AND r.status = 'active';

INSERT IGNORE INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id FROM roles r JOIN permissions p ON p.code = 'attachment.manage'
WHERE r.code = 'breed_worker' AND r.status = 'active';

INSERT INTO areas (organization_id, farm_id, code, name, parent_id, status, sort_order)
SELECT organization.id, farm.id, seed.code, seed.name, NULL, 'verified', seed.sort_order
FROM organizations AS organization
INNER JOIN farms AS farm ON farm.organization_id = organization.id AND farm.code = 'default-farm'
CROSS JOIN (
  SELECT 'north-farm' AS code, '北区基地' AS name, 10 AS sort_order
  UNION ALL
  SELECT 'south-farm', '南区基地', 20
) AS seed
WHERE organization.code = 'default'
ON DUPLICATE KEY UPDATE
  organization_id = VALUES(organization_id), farm_id = VALUES(farm_id), name = VALUES(name),
  status = VALUES(status), sort_order = VALUES(sort_order), updated_at = CURRENT_TIMESTAMP;

-- 数据范围字典：全场 / 区域 / 个人 三级
INSERT INTO data_scopes (code, name, scope_type, area_id, status)
SELECT 'farm-all', '全场数据（所有基地）', 'farm', NULL, 'active'
WHERE NOT EXISTS (SELECT 1 FROM data_scopes WHERE code = 'farm-all');

INSERT INTO data_scopes (code, name, scope_type, area_id, status)
SELECT 'personal-self', '仅本人数据', 'personal', NULL, 'active'
WHERE NOT EXISTS (SELECT 1 FROM data_scopes WHERE code = 'personal-self');

INSERT INTO data_scopes (code, name, scope_type, area_id, status)
SELECT CONCAT(a.code, '-all'), CONCAT(a.name, '全部数据'), 'area', a.id, 'active'
FROM areas AS a
WHERE NOT EXISTS (SELECT 1 FROM data_scopes AS existing WHERE existing.code = CONCAT(a.code, '-all'));

INSERT INTO permissions (code, name, module_code, description)
VALUES
  ('cost.view', '查看成本核算', 'cost', '查看九类成本、来源明细与分摊规则'),
  ('cost.allocation.manage', '管理成本分摊规则', 'cost', '创建新的成本分摊规则版本')
ON DUPLICATE KEY UPDATE
  name = VALUES(name), module_code = VALUES(module_code), description = VALUES(description), updated_at = CURRENT_TIMESTAMP;

INSERT INTO role_permissions (role_id, permission_id)
SELECT r.id, p.id
FROM roles AS r
CROSS JOIN permissions AS p
LEFT JOIN role_permissions AS existing ON existing.role_id = r.id AND existing.permission_id = p.id
WHERE existing.role_id IS NULL
  AND r.status = 'active'
  AND ((p.code = 'cost.view' AND r.code IN ('super_admin', 'breed_manager', 'finance_staff'))
    OR (p.code = 'cost.allocation.manage' AND r.code IN ('super_admin', 'finance_staff')));
