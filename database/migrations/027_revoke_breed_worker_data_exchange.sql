SET NAMES utf8mb4;

-- 017/018 已发布后，breed_worker 仅保留现场附件能力；撤销误授的数据交换权限。
DELETE rp FROM role_permissions rp
INNER JOIN roles r ON r.id = rp.role_id
INNER JOIN permissions p ON p.id = rp.permission_id
WHERE r.code='breed_worker'
  AND p.code IN ('data_exchange.view','data_exchange.export');
