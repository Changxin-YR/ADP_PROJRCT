/**
 * 塘小助的「人话」词汇表：接口路径、工具名、字段英文名 → 业务人员看得懂的中文。
 *
 * 与 backend/layers/features/agent/agent_humanize.py 共用同一套措辞。前端只在后端
 * 没给出 summary / target / changes 时兜底；两边叫法必须一致，同一件事不能有两种说法。
 * 这里只放词表（纯数据），翻译逻辑在 agent.humanize.ts，便于单测。
 */

/** 业务域 → 中文名（接口路径第一段）。 */
export const DOMAIN_LABELS: Record<string, string> = {
  production: '生产记录', 'master-data': '档案', master_data: '档案', warehouse: '仓储单据',
  purchase: '采购单据', sales: '销售单据', cost: '成本单据', workbench: '待办事项',
  'data-exchange': '数据交换', data_exchange: '数据交换', admin: '账号与权限', auth: '登录账号',
  agent: '智能助手', ponds: '塘口档案',
}

/** 资源段（路径或 arguments.resource）→ 中文名。 */
export const RESOURCE_LABELS: Record<string, string> = {
  ponds: '塘口档案', areas: '片区档案', 'pond-groups': '塘口分组', farms: '养殖场档案',
  materials: '物料档案', partners: '业务伙伴', customers: '客户档案', suppliers: '供应商档案',
  medications: '药品档案', species: '养殖品种',
  samplings: '抽样记录', transfers: '转塘记录', losses: '损耗记录', harvests: '出塘记录',
  'feed-plans': '投喂计划', 'feed-tasks': '投喂任务', 'feed-logs': '投喂记录', feedings: '投喂记录',
  feeding: '投喂记录', 'daily-operations': '日常巡塘', batches: '养殖批次',
  issues: '出库单', receipts: '入库单', stocktakes: '盘点单', scraps: '报废单', alerts: '库存预警',
  ledgers: '库存台账', records: '业务记录',
  entries: '成本分录', expenses: '费用单', assets: '资产卡片', settlements: '期间结算',
  allocations: '成本分摊', reports: '报表',
  orders: '单据', payments: '付款记录', returns: '退货单',
  'work-items': '待办事项', notifications: '通知', summary: '工作台摘要',
  imports: '导入批次', templates: '导入模板', attachments: '附件', exports: '导出任务',
  users: '系统账号', roles: '角色', applications: '注册申请', 'audit-logs': '操作日志',
}

/** 字段英文名 → 中文标签。后端缺 changes 时由前端兜底。 */
export const FIELD_LABELS: Record<string, string> = {
  resource: '对象类型', resource_type: '对象类型', pond_id: '塘口', pond_code: '塘口编码',
  pond_name: '塘口名称', pond_ids: '塘口范围', area_id: '片区', area_name: '片区名称',
  pond_group_id: '塘口分组', farm_id: '养殖场',
  batch_id: '批次', batch_code: '批次编号', batch_status: '批次状态', code: '编码', name: '名称',
  id: '编号', record_id: '记录', entry_id: '分录', expense_id: '费用单', settlement_id: '结算单',
  asset_id: '资产卡片', order_id: '单据', material_id: '物料', material_name: '物料名称',
  partner_id: '业务伙伴', supplier_id: '供应商', customer_id: '客户', operator_id: '经办人',
  manager_id: '负责人', manager_name: '负责人',
  species: '养殖品种', current_spec: '当前规格', stocking_spec: '投苗规格',
  quantity: '数量', stock_quantity: '存塘数量', quantity_delta: '数量变动',
  weight_kg: '重量（kg）', avg_weight_kg: '平均体重（kg）', weight_delta_kg: '重量变动（kg）',
  unit_price: '单价', amount: '金额', total_amount: '合计金额', payment_amount: '付款金额',
  received_amount: '收款金额', tax_rate: '税率',
  happened_at: '发生时间', occurred_at: '发生时间', expected_at: '预计时间', due_date: '到期日',
  started_at: '开始时间', finished_at: '完成时间', created_at: '创建时间', updated_at: '更新时间',
  verified_at: '核验时间',
  status: '状态', status_text: '状态', note: '说明', notes: '备注', reason: '原因', remark: '备注',
  loss_reason: '损耗原因', location: '位置', location_text: '位置', capacity_mu: '养殖面积（亩）',
  water_source: '水源', aerator_count: '增氧机数量',
  attachment_id: '附件', template_code: '模板', expected_version: '数据版本', row_version: '数据版本',
  phone: '手机号', login_name: '登录名', role_ids: '角色', permissions: '权限', user_id: '账号',
  application_id: '注册申请', role_id: '角色', scope_type: '范围类型', scope_id: '范围对象',
  method: '方式', category: '分类', type: '类型', source: '来源', target: '目标', department: '部门',
  page: '页码', page_size: '每页条数', keyword: '关键词', search: '搜索词', status_filter: '状态筛选',
  uninspected_on: '未巡检日期', total: '合计', unit: '单位', price: '单价', remark_text: '备注',
}

/** 状态/枚举值 → 中文。 */
export const VALUE_LABELS: Record<string, string> = {
  pending: '待确认', confirmed: '已确认', active: '已启用', inactive: '已停用', disabled: '已停用',
  draft: '草稿', submitted: '已提交', verified: '已核验', rejected: '已驳回', approved: '已审批',
  cancelled: '已取消', canceled: '已取消', expired: '已过期', failed: '未成功', failure: '未成功',
  success: '成功', done: '已完成', processing: '处理中', open: '待处理', closed: '已关闭',
  normal: '正常', warning: '预警', danger: '预警', high: '高风险', low: '低风险', medium: '中风险',
  today: '今天', yesterday: '昨天', yes: '是', no: '否', true: '是', false: '否',
}

/** 兜底翻译用的单词表：未知字段下划线转空格前，先尽量翻成中文。 */
export const WORD_LABELS: Record<string, string> = {
  stock: '库存', quantity: '数量', qty: '数量', count: '数量', num: '数量', number: '编号',
  code: '编码', name: '名称', id: '编号', no: '编号', total: '合计', amount: '金额', price: '单价',
  unit: '单位', weight: '重量', kg: '千克', mu: '亩', date: '日期', time: '时间', at: '时间',
  status: '状态', text: '说明', type: '类型', source: '来源', remark: '备注', note: '说明',
  pond: '塘口', batch: '批次', feed: '投喂', feeding: '投喂', logs: '记录', log: '记录',
  material: '物料', partner: '伙伴', customer: '客户', supplier: '供应商', order: '单据',
  entry: '分录', expense: '费用', asset: '资产', settlement: '结算', warehouse: '仓储',
  production: '生产', cost: '成本', purchase: '采购', sales: '销售', work: '待办', item: '事项',
  created: '创建', updated: '更新', happened: '发生', verified: '核验', expected: '预计',
  start: '开始', finish: '完成', version: '版本', page: '页码', size: '条数', keyword: '关键词',
  reason: '原因', loss: '损耗', area: '片区', farm: '养殖场', species: '品种', user: '账号',
}

/** HTTP 方法 → 动词。 */
export const METHOD_VERBS: Record<string, string> = {
  GET: '查询', POST: '新增', PUT: '保存', PATCH: '修改', DELETE: '删除',
}

/** 工具名里的操作词 → 中文动词。 */
export const OPERATION_VERBS: Record<string, string> = {
  list: '查询', query: '查询', get: '查看', detail: '查看', create: '新增', add: '新增',
  update: '修改', edit: '修改', patch: '修改', put: '保存', save: '保存', delete: '删除',
  remove: '删除', submit: '提交', verify: '核验', confirm: '确认', approve: '审批',
  reject: '驳回', receive: '收货', deliver: '发货', dispatch: '发出', cancel: '取消',
  reverse: '冲销', depreciate: '计提折旧', preview: '预检', revoke: '撤销', export: '导出',
  import: '导入', status: '变更状态', post: '新增', copy: '复制', copies: '复制', reset: '重置',
  retire: '停用', review: '审核', set: '调整', grant: '调整授权',
}

/** 已知工具名 → 动词（后端工具命名是稳定的，兜底时先查这里）。 */
export const TOOL_VERBS: Record<string, string> = {
  'master_data.list_records': '查询', 'master_data.create_record': '新增', 'master_data.get_record': '查看',
  'production.list_records': '查询', 'warehouse.list_records': '查询', 'purchase.list_orders': '查询',
  'sales.list_orders': '查询', 'cost.list_entries': '查询', 'data_exchange.preview_import': '预检',
  'workbench.list_work_items': '查询', 'workbench.update_work_item': '处理',
  'admin.create_user': '新增', 'admin.update_role_permissions': '调整', 'admin.update_grants': '调整',
  'admin.set_status': '调整', 'admin.reset_password': '重置', 'admin.retire_user': '停用',
  'admin.review_application': '审核',
}

/** 路径末段 → 中文动作（提交/核验/确认…）。 */
export const PATH_TAILS: Record<string, string> = {
  submit: '提交', verify: '核验', confirm: '确认', revoke: '撤销', archive: '归档', approve: '审批',
  reject: '驳回', receive: '收货', deliver: '发货', dispatch: '发出', cancel: '取消', reverse: '冲销',
  depreciate: '计提折旧', status: '变更', copies: '复制', permissions: '调整权限', grants: '调整授权',
  'reset-password': '重置密码', 'password-reset': '重置密码', retire: '停用', 'status-changes': '申请',
}

/**
 * 路径 → 中文动作表。`{xxx}` 表示任意一段，匹配时按通配处理。
 * 没有命中的条目再由「方法动词 + 资源中文名」拼出来。
 */
export const PATH_ACTIONS: Record<string, string> = {
  'POST /api/v1/production/{resource}': '新增生产记录',
  'PUT /api/v1/production/{resource}': '保存生产记录',
  'PATCH /api/v1/production/{resource}': '修改生产记录',
  'DELETE /api/v1/production/{resource}': '删除生产记录',
  'POST /api/v1/master-data/ponds': '新增塘口档案',
  'POST /api/v1/master-data/ponds/{pond_id}/status-changes': '申请塘口状态变更',
  'POST /api/v1/production/batches/{batch_id}/status': '变更批次状态',
  'POST /api/v1/data-exchange/imports/preview': '预检导入文件',
  'POST /api/v1/data-exchange/imports/{batch_id}/confirm': '确认导入',
  'POST /api/v1/cost/allocations': '执行成本分摊',
  'POST /api/v1/admin/users': '新增账号',
  'PUT /api/v1/admin/roles/{role_id}/permissions': '调整角色权限',
}

/** 列表/总数/名称/编码/时间类键名：从业务对象里挑人话用的。 */
export const LIST_KEYS: readonly string[] = ['items', 'records', 'rows', 'list', 'results', 'data']
export const COUNT_KEYS: readonly string[] = ['total', 'count', 'total_count', 'total_count_value']
export const NAME_KEYS: readonly string[] = ['name', 'pond_name', 'material_name', 'partner_name', 'customer_name', 'supplier_name', 'title']
export const CODE_KEYS: readonly string[] = ['code', 'pond_code', 'batch_code', 'entry_no', 'order_no', 'doc_no', 'record_no', 'no']
export const TIME_KEYS: readonly string[] = ['happened_at', 'occurred_at', 'created_at', 'updated_at', 'due_date', 'date']

/** 追踪类字段：永远不进入正文（只允许出现在 hover 提示里）。 */
export const TRACKING_KEYS: readonly string[] = [
  'request_id', 'session_id', 'conversation_id', 'trace_id', 'idempotency_key', 'tool_name',
  'token', 'csrf_token', 'status_code',
]
