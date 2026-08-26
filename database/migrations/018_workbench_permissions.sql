SET NAMES utf8mb4;

INSERT INTO permissions (code,name,module_code,description) VALUES
  ('workbench.enter','进入工作台','workbench','查看按角色权限和数据范围聚合的工作台')
ON DUPLICATE KEY UPDATE
  name=VALUES(name),module_code=VALUES(module_code),description=VALUES(description);

INSERT IGNORE INTO role_permissions (role_id,permission_id)
SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
WHERE r.status='active' AND (
  (r.code IN ('super_admin','breed_manager','breed_worker','warehouse_manager','purchaser','finance_staff','sales_staff')
    AND p.code IN ('workbench.enter','work_item.view','work_item.manage')) OR
  (r.code IN ('super_admin','breed_manager','breed_worker','warehouse_manager','purchaser','finance_staff','sales_staff')
    AND p.code='master_data.view') OR
  (r.code IN ('super_admin','breed_manager','breed_worker','warehouse_manager','finance_staff','sales_staff')
    AND p.code='production.view') OR
  (r.code IN ('super_admin','breed_manager','breed_worker','warehouse_manager','purchaser','finance_staff')
    AND p.code='warehouse.view') OR
  (r.code IN ('super_admin','warehouse_manager','purchaser','finance_staff') AND p.code='purchase.view') OR
  (r.code IN ('super_admin','breed_manager','finance_staff','sales_staff') AND p.code='sales.view') OR
  (r.code IN ('super_admin','breed_manager','finance_staff') AND p.code='cost.view') OR
  (r.code IN ('super_admin','breed_manager','warehouse_manager','purchaser','finance_staff','sales_staff')
    AND p.code IN ('data_exchange.view','data_exchange.export','attachment.manage'))
);

-- 修正 017 中误写为 finance 的角色码；只补授权，不改写历史迁移。
INSERT IGNORE INTO role_permissions (role_id,permission_id)
SELECT r.id,p.id FROM roles r CROSS JOIN permissions p
WHERE r.code='finance_staff' AND p.code IN ('data_exchange.view','data_exchange.export','attachment.manage');
