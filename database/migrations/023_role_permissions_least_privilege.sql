SET NAMES utf8mb4;

-- BUG-M1-002~004 最小权限收缩（least privilege）
-- 仅删除下列过度授权，其余授权保持原样：
--   breed_worker      × warehouse.view / sales.view
--   warehouse_manager × production.view
--   breed_manager     × sales.view
-- 注意：breed_manager 的 production.view 保留（养殖管理员必须查看生产业务）。
DELETE rp FROM role_permissions rp
INNER JOIN roles r ON r.id = rp.role_id
INNER JOIN permissions p ON p.id = rp.permission_id
WHERE (
  (r.code = 'breed_worker' AND p.code IN ('warehouse.view', 'sales.view'))
  OR (r.code = 'warehouse_manager' AND p.code = 'production.view')
  OR (r.code = 'breed_manager' AND p.code = 'sales.view')
);
