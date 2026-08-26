SET NAMES utf8mb4;

-- Account review and administration are super-admin responsibilities.
DELETE role_permission
FROM role_permissions AS role_permission
INNER JOIN roles AS role_record ON role_record.id = role_permission.role_id
INNER JOIN permissions AS permission_record ON permission_record.id = role_permission.permission_id
WHERE role_record.code = 'breed_manager'
  AND permission_record.code IN ('auth.review', 'auth.user.manage');

UPDATE roles
SET description = '全场/区域养殖生产管理与业务审核'
WHERE code = 'breed_manager';
