export interface NavItem { to: string; label: string; requiredPermission?: string; count?: number; countTone?: 'teal' | 'amber' | 'rose' }
export interface NavGroup { code: string; label: string; icon: string; items: NavItem[] }

export const navGroups: NavGroup[] = [
  { code: 'ponds-batches', label: '塘口与批次', icon: 'grid', items: [
    { to: '/ponds', label: '塘口档案', requiredPermission: 'master_data.view' }, { to: '/pond-groups', label: '塘口分组', requiredPermission: 'master_data.view' },
    { to: '/batches', label: '养殖批次', requiredPermission: 'production.view' }, { to: '/sampling', label: '规格抽样', requiredPermission: 'production.view' },
    { to: '/transfers', label: '转塘记录', requiredPermission: 'production.view' }, { to: '/losses', label: '损耗记录', requiredPermission: 'production.view' },
    { to: '/harvests', label: '出塘捕捞', requiredPermission: 'production.view' },
  ] },
  { code: 'daily-farming', label: '日常养殖', icon: 'cycle', items: [
    { to: '/feeding/plans', label: '喂养计划', requiredPermission: 'production.view' }, { to: '/feeding/tasks', label: '投喂任务', requiredPermission: 'production.view' },
    { to: '/feeding/logs', label: '投喂记录', requiredPermission: 'production.view' }, { to: '/daily-ops', label: '日常作业', requiredPermission: 'production.view' },
  ] },
  { code: 'warehouse', label: '物料与仓储', icon: 'layers', items: [
    { to: '/warehouse/materials', label: '物料档案', requiredPermission: 'warehouse.view' }, { to: '/warehouse/in', label: '入库管理', requiredPermission: 'warehouse.view' },
    { to: '/warehouse/out', label: '出库领用', requiredPermission: 'warehouse.view' }, { to: '/warehouse/returns', label: '退库管理', requiredPermission: 'warehouse.view' },
    { to: '/warehouse/transfers', label: '仓间调拨', requiredPermission: 'warehouse.view' }, { to: '/warehouse/stocktakes', label: '库存盘点', requiredPermission: 'warehouse.view' },
    { to: '/warehouse/scraps', label: '报损报废', requiredPermission: 'warehouse.view' }, { to: '/warehouse/alerts', label: '库存预警', requiredPermission: 'warehouse.view' },
    { to: '/warehouse/ledger', label: '仓储台账', requiredPermission: 'warehouse.view' },
  ] },
  { code: 'purchase', label: '采购与付款', icon: 'swap', items: [
    { to: '/purchase/suppliers', label: '供应商档案', requiredPermission: 'purchase.view' }, { to: '/purchase/orders', label: '采购明细', requiredPermission: 'purchase.view' },
    { to: '/purchase/payables', label: '应付账款', requiredPermission: 'finance.payable.view' },
  ] },
  { code: 'sales', label: '销售与收款', icon: 'target', items: [
    { to: '/sales/customers', label: '客户档案', requiredPermission: 'sales.view' }, { to: '/sales/orders', label: '销售明细', requiredPermission: 'sales.view' },
    { to: '/sales/receivables', label: '应收账款', requiredPermission: 'finance.receivable.view' },
  ] },
  { code: 'cost', label: '成本与经营', icon: 'diamond', items: [
    { to: '/cost/structure', label: '成本构成', requiredPermission: 'cost.view' },
    { to: '/cost/expenses', label: '费用登记', requiredPermission: 'cost.view' },
    { to: '/cost/assets', label: '资产台账', requiredPermission: 'cost.view' },
    { to: '/cost/settlements', label: '期间结算', requiredPermission: 'cost.view' },
  ] },
  { code: 'data', label: '数据交换', icon: 'exchange', items: [
    { to: '/data/templates', label: '导入模板', requiredPermission: 'data_exchange.view' }, { to: '/data/imports', label: '批量导入', requiredPermission: 'data_exchange.view' },
  ] },
  { code: 'admin', label: '系统管理', icon: 'gear', items: [
    { to: '/admin/users', label: '用户管理', requiredPermission: 'auth.user.manage' },
    { to: '/admin/applications', label: '注册审核', requiredPermission: 'auth.review' },
    { to: '/admin/roles', label: '角色权限', requiredPermission: 'auth.role.manage' },
    { to: '/admin/logs', label: '操作日志', requiredPermission: 'audit.view' },
    { to: '/admin/settings', label: '业务参数', requiredPermission: 'auth.user.manage' },
  ] },
]

export const helpSections = [
  { title: '塘口与批次', body: '塘口档案支持状态有向流转（筹建→放养→养殖→轮休/清塘→改造），放养与清塘需双人核验；批次全程记录抽样、转塘、损耗与出塘，保证斤鱼成本可回溯。' },
  { title: '日常养殖', body: '喂养计划按周期生成投喂任务，任务完成后填写投喂记录；超出计划偏差阈值会生成异常提醒，可在消息与预警中处理。' },
  { title: '物料与仓储', body: '入库/出库/退库/调拨均走单据流程；低库存、临期、过期自动进入库存预警，处理动作直达补货、调拨或报废。' },
  { title: '采购与销售', body: '采购明细确认后生成应付账款，销售确认后生成应收账款；收付款登记后自动核销余额，逾期自动提醒。' },
  { title: '成本与结算', body: '成本按九大类归集，公共成本按分摊规则落到塘口；期间结算按月锁定数据，保证经营口径一致。' },
  { title: '数据与系统', body: '批量导入先校验预览，任一行失败整批回滚；角色权限决定数据范围，操作日志保留全部关键动作。' },
]
