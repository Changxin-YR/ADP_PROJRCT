// 全模块演示数据集：覆盖功能文档 ADP-FD-3.2 的九大导航区域。
// 后端 API 就绪前，各模块页面从本数据集读取；接口上线后可在 service 层切换。

export interface FeedPlan { id: number; code: string; target: string; species: string; stage: string; times_per_day: number; time_window: string; standard_amount: string; deviation: string; feed: string; effective: string; version: string; status: string }
export interface FeedTask { id: number; code: string; pond: string; plan_amount: number; actual_amount: number | null; unit: string; worker: string; due_at: string; status: string; priority: string; deviation_note: string }
export interface FeedLog { id: number; logged_at: string; pond: string; batch: string; feed: string; plan_amount: number; actual_amount: number; unit: string; worker: string; weather: string; appetite: string; review_status: string; note: string }
export interface DailyOp { id: number; code: string; type: string; pond: string; content: string; result: string; operator: string; happened_at: string; status: string }
export interface Sampling { id: number; code: string; pond: string; batch: string; sample_count: number; avg_spec: string; estimated_stock: string; method: string; delta: string; reviewer: string; happened_at: string }
export interface Loss { id: number; code: string; pond: string; batch: string; type: string; quantity: string; reason: string; founder: string; reviewer: string; happened_at: string; status: string }
export interface Transfer { id: number; code: string; from_pond: string; to_pond: string; batch: string; quantity: string; spec: string; operator: string; verifier: string; happened_at: string; status: string }
export interface Harvest { id: number; code: string; pond: string; batch: string; species: string; quantity: string; destination: string; operator: string; verifier: string; happened_at: string; status: string }
export interface Material { id: number; code: string; name: string; category: string; spec: string; unit: string; price: number; supplier: string; stock: number; safety_stock: number; shelf_days: number; location: string; status: string }
export interface StockIn { id: number; code: string; material: string; quantity: string; type: string; batch_no: string; expire_at: string; supplier: string; location: string; operator: string; happened_at: string; status: string }
export interface StockOut { id: number; code: string; material: string; quantity: string; scene: string; pond: string; receiver: string; approver: string; batch_split: string; happened_at: string; status: string }
export interface StockReturn { id: number; code: string; source: string; material: string; quantity: string; reason: string; returner: string; receiver: string; happened_at: string; status: string }
export interface StockTransfer { id: number; code: string; from_warehouse: string; to_warehouse: string; material: string; quantity: string; status: string; in_transit: string; operator: string; happened_at: string }
export interface Stocktake { id: number; code: string; type: string; material: string; book_qty: string; actual_qty: string; diff: string; reason: string; counter: string; reviewer: string; happened_at: string; status: string }
export interface Scrap { id: number; code: string; material: string; batch_no: string; quantity: string; reason: string; applicant: string; reviewer: string; happened_at: string; status: string }
export interface StockAlert { id: number; material: string; type: string; level: string; current: string; threshold: string; happened_at: string; status: string }
export interface StockLedger { id: number; happened_at: string; material: string; batch_no: string; biz_type: string; quantity: string; pond: string; operator: string; doc_no: string }
export interface Supplier { id: number; code: string; name: string; contact: string; phone: string; main_items: string; cooperation: string; settle_cycle: string; total_purchase: number; payable_balance: number }
export interface Purchase { id: number; code: string; supplier: string; material: string; quantity: string; unit_price: number; amount: number; paid: number; due_at: string; status: string }
export interface Payable { id: number; supplier: string; doc_no: string; amount: number; paid: number; unpaid: number; due_at: string; overdue_days: number; status: string }
export interface Customer { id: number; code: string; name: string; contact: string; phone: string; preference: string; cooperation: string; settle_cycle: string; credit_limit: string; total_sales: number; receivable_balance: number }
export interface Sale { id: number; code: string; customer: string; pond: string; batch: string; species: string; quantity: string; unit_price: number; amount: number; received: number; deliver_status: string; happened_at: string }
export interface Receivable { id: number; customer: string; doc_no: string; amount: number; received: number; unreceived: number; due_at: string; overdue_days: number; status: string }
export interface CostItem { category: string; amount: number; basis: string; share_note: string; share: number }
export interface Expense { id: number; code: string; category: string; amount: number; happened_at: string; party: string; scope: string; basis: string; status: string }
export interface Asset { id: number; code: string; name: string; category: string; value: number; years: number; status: string; owner_scope: string; note: string }
export interface Settlement { id: number; period: string; income: number; cost: number; profit: number; status: string; operator: string; settled_at: string; note: string }
export interface TemplateItem { id: number; name: string; group: string; fields: number; updated_at: string }
export interface ImportBatch { id: number; happened_at: string; data_type: string; file_name: string; rows: number; passed: number; failed: number; status: string; operator: string }
export interface RoleRow { id: number; name: string; code: string; users: number; summary: string; data_scope: string; status: string }
export interface OpLog { id: number; happened_at: string; user: string; action: string; target: string; result: string; detail: string }
export interface SettingGroup { group: string; items: { name: string; value: string; note: string }[] }

export const feedPlans: FeedPlan[] = [
  { id: 1, code: 'FP-2026-018', target: '东港主养区（分组）', species: '南美白对虾', stage: '中虾期', times_per_day: 3, time_window: '06:30 / 11:00 / 16:30', standard_amount: '45 kg/次·塘', deviation: '±10%', feed: '虾配合饲料 1.0mm', effective: '2026-08-01 ~ 2026-09-15', version: 'V3', status: '执行中' },
  { id: 2, code: 'FP-2026-016', target: '东港一号塘', species: '南美白对虾', stage: '成虾期', times_per_day: 2, time_window: '07:00 / 16:00', standard_amount: '30 kg/次', deviation: '±8%', feed: '虾配合饲料 1.5mm', effective: '2026-07-15 ~ 2026-09-20', version: 'V2', status: '执行中' },
  { id: 3, code: 'FP-2026-021', target: '东港二号塘', species: '南美白对虾', stage: '苗期', times_per_day: 4, time_window: '06:00 / 10:00 / 14:00 / 18:00', standard_amount: '12 kg/次', deviation: '±5%', feed: '虾苗开口料 0.5mm', effective: '2026-07-05 ~ 2026-08-30', version: 'V1', status: '执行中' },
  { id: 4, code: 'FP-2026-012', target: '南湾育苗塘', species: '加州鲈', stage: '育苗期', times_per_day: 3, time_window: '07:30 / 12:30 / 17:30', standard_amount: '8 kg/次', deviation: '±10%', feed: '鲈鱼苗料 1.0mm', effective: '2026-03-10 ~ 2026-08-18', version: 'V4', status: '已结束' },
  { id: 5, code: 'FP-2026-024', target: '全场（高温预案）', species: '通用', stage: '高温调整', times_per_day: 2, time_window: '06:00 / 17:30', standard_amount: '按标准量 70%', deviation: '可下调 30%', feed: '按各塘计划', effective: '2026-07-20 ~ 2026-08-31', version: 'V1', status: '执行中' },
]

export const feedTasks: FeedTask[] = [
  { id: 1, code: 'FT-0815-01', pond: '东港一号塘', plan_amount: 90, actual_amount: 86, unit: 'kg', worker: '陈志强', due_at: '今天 16:30', status: '已核验', priority: '普通', deviation_note: '偏差 -4.4%，摄食偏弱' },
  { id: 2, code: 'FT-0815-02', pond: '东港二号塘', plan_amount: 48, actual_amount: 48, unit: 'kg', worker: '陈志强', due_at: '今天 18:00', status: '待核验', priority: '普通', deviation_note: '按计划完成' },
  { id: 3, code: 'FT-0815-03', pond: '东港一号塘', plan_amount: 45, actual_amount: null, unit: 'kg', worker: '周敏', due_at: '今天 17:00', status: '执行中', priority: '普通', deviation_note: '作业员已接单' },
  { id: 4, code: 'FT-0815-04', pond: '南湾育苗塘', plan_amount: 24, actual_amount: null, unit: 'kg', worker: '未指派', due_at: '明天 07:30', status: '待执行', priority: '高', deviation_note: '育苗期重点关注' },
  { id: 5, code: 'FT-0814-09', pond: '东港二号塘', plan_amount: 48, actual_amount: 52, unit: 'kg', worker: '周敏', due_at: '昨天 18:00', status: '已复盘', priority: '普通', deviation_note: '偏差 +8.3%，天气转晴摄食旺' },
  { id: 6, code: 'FT-0813-06', pond: '南湾轮休塘', plan_amount: 20, actual_amount: null, unit: 'kg', worker: '陈志强', due_at: '08-13 16:00', status: '已取消', priority: '低', deviation_note: '塘口进入轮休，取消投喂' },
]

export const feedLogs: FeedLog[] = [
  { id: 1, logged_at: '2026-08-15 16:35', pond: '东港一号塘', batch: 'ADP-2026-001', feed: '虾配合饲料 1.5mm', plan_amount: 45, actual_amount: 43, unit: 'kg', worker: '陈志强', weather: '多云 29℃', appetite: '正常', review_status: '待审核', note: '—' },
  { id: 2, logged_at: '2026-08-15 11:10', pond: '东港二号塘', batch: 'ADP-2026-002', feed: '虾苗开口料 0.5mm', plan_amount: 12, actual_amount: 12, unit: 'kg', worker: '陈志强', weather: '多云 29℃', appetite: '正常', review_status: '已审核', note: '—' },
  { id: 3, logged_at: '2026-08-15 07:05', pond: '东港一号塘', batch: 'ADP-2026-001', feed: '虾配合饲料 1.5mm', plan_amount: 45, actual_amount: 31, unit: 'kg', worker: '周敏', weather: '阴 26℃', appetite: '少食', review_status: '异常待处理', note: '溶氧偏低，减量投喂' },
  { id: 4, logged_at: '2026-08-14 17:40', pond: '东港二号塘', batch: 'ADP-2026-002', feed: '虾苗开口料 0.5mm', plan_amount: 12, actual_amount: 13, unit: 'kg', worker: '周敏', weather: '晴 31℃', appetite: '抢食', review_status: '已审核', note: '—' },
  { id: 5, logged_at: '2026-08-13 16:20', pond: '东港一号塘', batch: 'ADP-2026-001', feed: '虾配合饲料 1.5mm', plan_amount: 45, actual_amount: 0, unit: 'kg', worker: '陈志强', weather: '暴雨 24℃', appetite: '拒食', review_status: '已审核', note: '暴雨停喂，符合高温/雨天预案' },
]

export const dailyOps: DailyOp[] = [
  { id: 1, code: 'OP-0815-11', type: '巡塘', pond: '东港一号塘', content: '水面平静，鱼群活动正常，未见死鱼', result: '正常', operator: '周敏', happened_at: '2026-08-15 06:40', status: '已确认' },
  { id: 2, code: 'OP-0815-09', type: '水质检测', pond: '东港一号塘', content: '溶氧 4.8mg/L，氨氮 0.32mg/L，pH 7.6', result: '溶氧偏低', operator: '周敏', happened_at: '2026-08-15 07:10', status: '异常跟进中' },
  { id: 3, code: 'OP-0815-07', type: '增氧', pond: '东港一号塘', content: '2 号增氧机运行 3 小时，应对溶氧偏低', result: '溶氧回升至 5.6mg/L', operator: '陈志强', happened_at: '2026-08-15 07:20', status: '已确认' },
  { id: 4, code: 'OP-0814-15', type: '用药', pond: '东港二号塘', content: '聚维酮碘全池泼洒消毒，用量按说明 0.3ppm', result: '完成，安全间隔期 7 天', operator: '陈志强', happened_at: '2026-08-14 15:00', status: '已确认' },
  { id: 5, code: 'OP-0814-10', type: '换水', pond: '东港二号塘', content: '换水 20cm，水源为东港主渠', result: '完成，进出水平衡', operator: '周敏', happened_at: '2026-08-14 09:00', status: '已确认' },
  { id: 6, code: 'OP-0812-04', type: '设备维护', pond: '南湾育苗塘', content: '1 号增氧机电机异响，更换轴承', result: '修复完成', operator: '外协·王工', happened_at: '2026-08-12 14:30', status: '已确认' },
]

export const samplings: Sampling[] = [
  { id: 1, code: 'SP-0814-02', pond: '东港一号塘', batch: 'ADP-2026-001', sample_count: 60, avg_spec: '11.2g / 42 尾·斤', estimated_stock: '约 152,400 尾', method: '抛网抽样', delta: '较上次 +0.8g', reviewer: '李海宁', happened_at: '2026-08-14' },
  { id: 2, code: 'SP-0807-01', pond: '东港一号塘', batch: 'ADP-2026-001', sample_count: 55, avg_spec: '10.4g / 46 尾·斤', estimated_stock: '约 153,100 尾', method: '抛网抽样', delta: '较上次 +1.1g', reviewer: '李海宁', happened_at: '2026-08-07' },
  { id: 3, code: 'SP-0813-03', pond: '东港二号塘', batch: 'ADP-2026-002', sample_count: 40, avg_spec: '3.6g / 139 尾·斤', estimated_stock: '约 159,200 尾', method: '苗箱计数', delta: '较上次 +0.9g', reviewer: '周敏', happened_at: '2026-08-13' },
]

export const losses: Loss[] = [
  { id: 1, code: 'LS-0813-01', pond: '东港一号塘', batch: 'ADP-2026-001', type: '疾病损耗', quantity: '860 尾 / 约 9.5kg', reason: '白斑综合征早期，已用药控制', founder: '周敏', reviewer: '李海宁', happened_at: '2026-08-13', status: '已确认' },
  { id: 2, code: 'LS-0811-02', pond: '东港一号塘', batch: 'ADP-2026-001', type: '缺氧浮头', quantity: '230 尾 / 约 2.6kg', reason: '夜间溶氧骤降', founder: '陈志强', reviewer: '李海宁', happened_at: '2026-08-11', status: '已确认' },
  { id: 3, code: 'LS-0809-01', pond: '东港二号塘', batch: 'ADP-2026-002', type: '抽样损耗', quantity: '40 尾', reason: '规格抽样取样', founder: '周敏', reviewer: '周敏', happened_at: '2026-08-09', status: '已确认' },
  { id: 4, code: 'LS-0815-03', pond: '东港一号塘', batch: 'ADP-2026-001', type: '逃逸', quantity: '待估', reason: '塘埂发现鼠洞，已修补', founder: '陈志强', reviewer: '待复核', happened_at: '2026-08-15', status: '待复核' },
]

export const transfers: Transfer[] = [
  { id: 1, code: 'TR-0810-01', from_pond: '南湾育苗塘', to_pond: '东港二号塘', batch: 'ADP-2026-002（分塘）', quantity: '60,000 尾', spec: '2.8g', operator: '周敏', verifier: '李海宁', happened_at: '2026-08-10', status: '已完成' },
  { id: 2, code: 'TR-0802-01', from_pond: '东港一号塘', to_pond: '东港二号塘', batch: 'ADP-2026-001（分批）', quantity: '20,000 尾', spec: '6.5g', operator: '陈志强', verifier: '李海宁', happened_at: '2026-08-02', status: '已完成' },
]

export const harvests: Harvest[] = [
  { id: 1, code: 'HV-0816-01', pond: '南湾育苗塘', batch: 'ADP-2026-003', species: '加州鲈', quantity: '6,800 斤', destination: '销售 → 杭州水产批发（拟）', operator: '周敏', verifier: '李海宁', happened_at: '2026-08-16（计划）', status: '待执行' },
  { id: 2, code: 'HV-0422-01', pond: '后勤清塘塘', batch: 'ADP-2025-014', species: '罗非鱼', quantity: '9,300 斤', destination: '销售 → 湖州客商', operator: '陈志强', verifier: '李海宁', happened_at: '2026-04-22', status: '已完成' },
]

export const materials: Material[] = [
  { id: 1, code: 'MT-001', name: '虾配合饲料 1.5mm', category: '饲料', spec: '40kg/袋', unit: '袋', price: 168, supplier: '海大饲料', stock: 42, safety_stock: 20, shelf_days: 180, location: '主仓 A-01', status: '正常' },
  { id: 2, code: 'MT-002', name: '虾苗开口料 0.5mm', category: '饲料', spec: '20kg/袋', unit: '袋', price: 132, supplier: '海大饲料', stock: 9, safety_stock: 15, shelf_days: 120, location: '主仓 A-02', status: '低库存' },
  { id: 3, code: 'MT-003', name: '鲈鱼配合饲料 2.0mm', category: '饲料', spec: '25kg/袋', unit: '袋', price: 210, supplier: '通威股份', stock: 0, safety_stock: 10, shelf_days: 180, location: '主仓 A-03', status: '低库存' },
  { id: 4, code: 'MT-011', name: '聚维酮碘溶液', category: '渔药', spec: '500ml/瓶', unit: '瓶', price: 26, supplier: '渔丰动保', stock: 36, safety_stock: 12, shelf_days: 540, location: '药品柜 B-01', status: '正常' },
  { id: 5, code: 'MT-012', name: '过硫酸氢钾底改片', category: '渔药', spec: '1kg/袋', unit: '袋', price: 38, supplier: '渔丰动保', stock: 18, safety_stock: 8, shelf_days: 90, location: '药品柜 B-02', status: '临期预警' },
  { id: 6, code: 'MT-021', name: '增氧机叶轮总成', category: '设备配件', spec: '1.5kW', unit: '套', price: 260, supplier: '农机服务站', stock: 4, safety_stock: 2, shelf_days: 0, location: '配件仓 C-01', status: '正常' },
  { id: 7, code: 'MT-031', name: '防护手套', category: '劳保工具', spec: '橡胶加厚', unit: '双', price: 6.5, supplier: '劳保用品店', stock: 60, safety_stock: 20, shelf_days: 0, location: '杂品仓 D-01', status: '正常' },
]

export const stockIns: StockIn[] = [
  { id: 1, code: 'IN-0812-05', material: '虾配合饲料 1.5mm', quantity: '+60 袋', type: '采购入库', batch_no: 'HD-260812', expire_at: '2027-02-08', supplier: '海大饲料', location: '主仓 A-01', operator: '吴仓管', happened_at: '2026-08-12', status: '已确认' },
  { id: 2, code: 'IN-0808-02', material: '聚维酮碘溶液', quantity: '+30 瓶', type: '采购入库', batch_no: 'YF-260808', expire_at: '2028-02-01', supplier: '渔丰动保', location: '药品柜 B-01', operator: '吴仓管', happened_at: '2026-08-08', status: '已确认' },
  { id: 3, code: 'IN-0806-01', material: '虾苗开口料 0.5mm', quantity: '+25 袋', type: '采购入库', batch_no: 'HD-260806', expire_at: '2026-12-04', supplier: '海大饲料', location: '主仓 A-02', operator: '吴仓管', happened_at: '2026-08-06', status: '已确认' },
  { id: 4, code: 'IN-0804-03', material: '过硫酸氢钾底改片', quantity: '+20 袋', type: '采购入库', batch_no: 'YF-260224', expire_at: '2026-09-01', supplier: '渔丰动保', location: '药品柜 B-02', operator: '吴仓管', happened_at: '2026-08-04', status: '已确认' },
]

export const stockOuts: StockOut[] = [
  { id: 1, code: 'OUT-0815-07', material: '虾配合饲料 1.5mm', quantity: '-6 袋', scene: '日常投喂', pond: '东港一号塘', receiver: '陈志强', approver: '李海宁', batch_split: '近效期优先：HD-260812 ×6', happened_at: '2026-08-15', status: '已确认' },
  { id: 2, code: 'OUT-0815-06', material: '虾苗开口料 0.5mm', quantity: '-2 袋', scene: '日常投喂', pond: '东港二号塘', receiver: '陈志强', approver: '李海宁', batch_split: 'HD-260806 ×2', happened_at: '2026-08-15', status: '已确认' },
  { id: 3, code: 'OUT-0814-04', material: '聚维酮碘溶液', quantity: '-4 瓶', scene: '用药', pond: '东港二号塘', receiver: '陈志强', approver: '李海宁', batch_split: 'YF-260808 ×4', happened_at: '2026-08-14', status: '已确认' },
  { id: 4, code: 'OUT-0812-02', material: '增氧机叶轮总成', quantity: '-1 套', scene: '设备维修', pond: '南湾育苗塘', receiver: '外协·王工', approver: '李海宁', batch_split: '—', happened_at: '2026-08-12', status: '已确认' },
  { id: 5, code: 'OUT-0815-08', material: '防护手套', quantity: '-10 双', scene: '其他用途', pond: '（不关联）', receiver: '周敏', approver: '待审批', batch_split: '—', happened_at: '2026-08-15', status: '待审批' },
]

export const stockReturns: StockReturn[] = [
  { id: 1, code: 'RT-0813-01', source: 'OUT-0813-06', material: '虾配合饲料 1.5mm', quantity: '+2 袋', reason: '当日计划调整，剩余退回', returner: '陈志强', receiver: '吴仓管', happened_at: '2026-08-13', status: '已验收' },
  { id: 2, code: 'RT-0810-02', source: 'OUT-0810-03', material: '过硫酸氢钾底改片', quantity: '+3 袋（破损 1 袋隔离）', reason: '领用超量，其中 1 袋包装破损', returner: '周敏', receiver: '吴仓管', happened_at: '2026-08-10', status: '部分可用' },
]

export const stockTransfers: StockTransfer[] = [
  { id: 1, code: 'TF-0811-01', from_warehouse: '主仓', to_warehouse: '南湾分仓', material: '虾配合饲料 1.5mm', quantity: '15 袋', status: '已完成', in_transit: '0', operator: '吴仓管 → 周敏', happened_at: '2026-08-11' },
  { id: 2, code: 'TF-0815-02', from_warehouse: '主仓', to_warehouse: '南湾分仓', material: '聚维酮碘溶液', quantity: '10 瓶', status: '在途', in_transit: '10 瓶', operator: '吴仓管 → 周敏', happened_at: '2026-08-15' },
]

export const stocktakes: Stocktake[] = [
  { id: 1, code: 'PD-0731-M', type: '月度盘点', material: '虾配合饲料 1.5mm', book_qty: '44 袋', actual_qty: '42 袋', diff: '-2 袋', reason: '包装破损散漏，已补报损', counter: '吴仓管', reviewer: '李海宁', happened_at: '2026-07-31', status: '差异已确认' },
  { id: 2, code: 'PD-0731-M', type: '月度盘点', material: '聚维酮碘溶液', book_qty: '36 瓶', actual_qty: '36 瓶', diff: '0', reason: '—', counter: '吴仓管', reviewer: '李海宁', happened_at: '2026-07-31', status: '一致' },
  { id: 3, code: 'PD-0815-T', type: '临时盘点', material: '虾苗开口料 0.5mm', book_qty: '9 袋', actual_qty: '9 袋', diff: '0', reason: '低库存触发临时盘点', counter: '吴仓管', reviewer: '待复核', happened_at: '2026-08-15', status: '待复核' },
]

export const scraps: Scrap[] = [
  { id: 1, code: 'SC-0815-01', material: '过硫酸氢钾底改片', batch_no: 'YF-260224', quantity: '-1 袋', reason: '包装破损受潮', applicant: '周敏', reviewer: '李海宁', happened_at: '2026-08-15', status: '已隔离待确认' },
  { id: 2, code: 'SC-0901-01', material: '过硫酸氢钾底改片', batch_no: 'YF-260224', quantity: '-16 袋（预计）', reason: '2026-09-01 到期，提前登记报废计划', applicant: '吴仓管', reviewer: '待复核', happened_at: '2026-09-01（计划）', status: '草稿' },
]

export const stockAlerts: StockAlert[] = [
  { id: 1, material: '虾苗开口料 0.5mm', type: '低库存', level: '高', current: '9 袋', threshold: '安全线 15 袋', happened_at: '2026-08-15', status: '待处理' },
  { id: 2, material: '鲈鱼配合饲料 2.0mm', type: '低库存', level: '高', current: '0 袋', threshold: '安全线 10 袋', happened_at: '2026-08-14', status: '待处理' },
  { id: 3, material: '过硫酸氢钾底改片', type: '临近到期', level: '中', current: '2026-09-01 到期（17 天）', threshold: '临期预警 30 天', happened_at: '2026-08-15', status: '处理中' },
  { id: 4, material: '虾配合饲料 1.5mm', type: '盘点差异', level: '低', current: '差异 -2 袋', threshold: '7 月月盘', happened_at: '2026-07-31', status: '已处理' },
]

export const stockLedger: StockLedger[] = [
  { id: 1, happened_at: '2026-08-15 16:30', material: '虾配合饲料 1.5mm', batch_no: 'HD-260812', biz_type: '出库·投喂', quantity: '-6 袋', pond: '东港一号塘', operator: '陈志强', doc_no: 'OUT-0815-07' },
  { id: 2, happened_at: '2026-08-15 11:00', material: '虾苗开口料 0.5mm', batch_no: 'HD-260806', biz_type: '出库·投喂', quantity: '-2 袋', pond: '东港二号塘', operator: '陈志强', doc_no: 'OUT-0815-06' },
  { id: 3, happened_at: '2026-08-15 09:00', material: '聚维酮碘溶液', batch_no: 'YF-260808', biz_type: '调拨发出', quantity: '-10 瓶', pond: '—（仓间）', operator: '吴仓管', doc_no: 'TF-0815-02' },
  { id: 4, happened_at: '2026-08-14 15:00', material: '聚维酮碘溶液', batch_no: 'YF-260808', biz_type: '出库·用药', quantity: '-4 瓶', pond: '东港二号塘', operator: '陈志强', doc_no: 'OUT-0814-04' },
  { id: 5, happened_at: '2026-08-13 17:00', material: '虾配合饲料 1.5mm', batch_no: 'HD-260812', biz_type: '退库', quantity: '+2 袋', pond: '东港一号塘', operator: '陈志强', doc_no: 'RT-0813-01' },
  { id: 6, happened_at: '2026-08-12 10:20', material: '虾配合饲料 1.5mm', batch_no: 'HD-260812', biz_type: '采购入库', quantity: '+60 袋', pond: '—（采购）', operator: '吴仓管', doc_no: 'IN-0812-05' },
]

export const suppliers: Supplier[] = [
  { id: 1, code: 'SUP-001', name: '海大饲料（东港经销处）', contact: '刘经理', phone: '138****2211', main_items: '虾料、鲈鱼料、苗料', cooperation: '合作中', settle_cycle: '月结 30 天', total_purchase: 486000, payable_balance: 61800 },
  { id: 2, code: 'SUP-002', name: '渔丰动保经营部', contact: '赵老板', phone: '137****8362', main_items: '渔药、消毒剂、水质改良剂', cooperation: '合作中', settle_cycle: '到货付款', total_purchase: 78400, payable_balance: 0 },
  { id: 3, code: 'SUP-003', name: '通威股份（区域直供）', contact: '孙经理', phone: '139****5077', main_items: '鲈鱼配合饲料', cooperation: '暂停合作', settle_cycle: '月结 15 天', total_purchase: 152000, payable_balance: 0 },
  { id: 4, code: 'SUP-004', name: '农机服务站', contact: '王师傅', phone: '136****9915', main_items: '增氧机及配件、维修服务', cooperation: '合作中', settle_cycle: '单结', total_purchase: 32700, payable_balance: 4200 },
]

export const purchases: Purchase[] = [
  { id: 1, code: 'PO-2026-031', supplier: '海大饲料', material: '虾配合饲料 1.5mm ×60 袋', quantity: '60 袋', unit_price: 168, amount: 10080, paid: 10080, due_at: '2026-09-11', status: '全部到货·已结清' },
  { id: 2, code: 'PO-2026-030', supplier: '海大饲料', material: '虾苗开口料 0.5mm ×25 袋', quantity: '25 袋', unit_price: 132, amount: 3300, paid: 1650, due_at: '2026-09-05', status: '全部到货·部分付款' },
  { id: 3, code: 'PO-2026-029', supplier: '渔丰动保', material: '聚维酮碘溶液 ×30 瓶 + 底改片 ×20 袋', quantity: '一批', unit_price: 32, amount: 1580, paid: 1580, due_at: '2026-08-08', status: '全部到货·已结清' },
  { id: 4, code: 'PO-2026-032', supplier: '通威股份', material: '鲈鱼配合饲料 2.0mm ×40 袋', quantity: '40 袋', unit_price: 210, amount: 8400, paid: 0, due_at: '—', status: '已取消' },
  { id: 5, code: 'PO-2026-033', supplier: '海大饲料', material: '虾配合饲料 1.5mm ×50 袋', quantity: '50 袋', unit_price: 168, amount: 8400, paid: 0, due_at: '2026-09-20', status: '采购中' },
]

export const payables: Payable[] = [
  { id: 1, supplier: '海大饲料', doc_no: 'PO-2026-030', amount: 3300, paid: 1650, unpaid: 1650, due_at: '2026-09-05', overdue_days: 0, status: '未到期' },
  { id: 2, supplier: '海大饲料', doc_no: 'PO-2026-027（历史）', amount: 61800, paid: 47600, unpaid: 14200, due_at: '2026-08-01', overdue_days: 14, status: '已逾期' },
  { id: 3, supplier: '农机服务站', doc_no: 'PO-2026-028', amount: 4200, paid: 0, unpaid: 4200, due_at: '2026-08-20', overdue_days: 0, status: '未到期' },
]

export const customers: Customer[] = [
  { id: 1, code: 'CUS-001', name: '杭州水产批发（许老板）', contact: '许卫东', phone: '135****6620', preference: '南美白对虾 30 头以上', cooperation: '活跃', settle_cycle: '出货后 7 天', credit_limit: '¥80,000', total_sales: 392000, receivable_balance: 46000 },
  { id: 2, code: 'CUS-002', name: '湖州鲜活水产商行', contact: '姚姐', phone: '139****3327', preference: '罗非鱼、加州鲈整塘', cooperation: '活跃', settle_cycle: '月结 15 天', credit_limit: '¥50,000', total_sales: 187500, receivable_balance: 0 },
  { id: 3, code: 'CUS-003', name: '本地零售·老陈', contact: '陈师傅', phone: '150****7198', preference: '零担现货，价格敏感', cooperation: '沉寂', settle_cycle: '现结', credit_limit: '¥5,000', total_sales: 42800, receivable_balance: 3200 },
]

export const sales: Sale[] = [
  { id: 1, code: 'SO-2026-018', customer: '杭州水产批发', pond: '东港一号塘', batch: 'ADP-2026-001', species: '南美白对虾', quantity: '2,000 斤（计划）', unit_price: 17.5, amount: 35000, received: 0, deliver_status: '待交付', happened_at: '2026-08-20（计划）' },
  { id: 2, code: 'SO-2026-017', customer: '杭州水产批发', pond: '东港一号塘', batch: 'ADP-2026-001', species: '南美白对虾', quantity: '1,600 斤', unit_price: 18.0, amount: 28800, received: 28800, deliver_status: '已交付·已结清', happened_at: '2026-08-05' },
  { id: 3, code: 'SO-2026-016', customer: '湖州鲜活水产商行', pond: '后勤清塘塘', batch: 'ADP-2025-014', species: '罗非鱼', quantity: '9,300 斤', unit_price: 6.4, amount: 59520, received: 59520, deliver_status: '已交付·已结清', happened_at: '2026-04-23' },
  { id: 4, code: 'SO-2026-015', customer: '本地零售·老陈', pond: '东港一号塘', batch: 'ADP-2026-001', species: '南美白对虾', quantity: '200 斤', unit_price: 16.0, amount: 3200, received: 0, deliver_status: '部分收款', happened_at: '2026-07-28' },
]

export const receivables: Receivable[] = [
  { id: 1, customer: '杭州水产批发', doc_no: 'SO-2026-015', amount: 3200, received: 0, unreceived: 3200, due_at: '2026-08-04', overdue_days: 11, status: '已逾期' },
  { id: 2, customer: '杭州水产批发', doc_no: 'SO-2026-014（历史）', amount: 42800, received: 0, unreceived: 42800, due_at: '2026-07-20', overdue_days: 26, status: '已逾期·跟进中' },
  { id: 3, customer: '本地零售·老陈', doc_no: 'SO-2026-013（历史）', amount: 3200, received: 3200, unreceived: 0, due_at: '2026-07-05', overdue_days: 0, status: '已结清' },
]

export const costItems: CostItem[] = [
  { category: '塘租', amount: 120000, basis: '按面积分摊', share_note: '全场 60 亩 · 2000 元/亩·年', share: 21.4 },
  { category: '设备', amount: 38000, basis: '按设备数量', share_note: '增氧机 14 台折旧 + 维护', share: 6.8 },
  { category: '基础建设', amount: 46000, basis: '按面积 + 年限', share_note: '塘埂修整 / 进排水改造', share: 8.2 },
  { category: '人工', amount: 144000, basis: '按工作范围', share_note: '固定 3 人 + 临时工', share: 25.7 },
  { category: '电费', amount: 42000, basis: '按设备运行时长', share_note: '峰谷计价 · 月度抄表', share: 7.5 },
  { category: '苗种', amount: 96000, basis: '按实际投入', share_note: '两批虾苗 + 鲈鱼苗', share: 17.1 },
  { category: '饲料', amount: 128000, basis: '按实际消耗', share_note: '入库领用流水汇总', share: 22.9 },
  { category: '动保', amount: 26000, basis: '按实际消耗', share_note: '渔药 + 消毒 + 水质改良', share: 4.6 },
  { category: '其他费用', amount: 32000, basis: '人工指定', share_note: '运输 / 检测 / 保险', share: 5.7 },
]

export const expenses: Expense[] = [
  { id: 1, code: 'EX-0812-01', category: '塘租', amount: 5000, happened_at: '2026-08-01', party: '村集体（东港片）', scope: '东港主养区', basis: '按面积分摊', status: '已确认' },
  { id: 2, code: 'EX-0812-02', category: '电费', amount: 8600, happened_at: '2026-08-05', party: '供电所', scope: '全场', basis: '按设备运行时长', status: '已确认' },
  { id: 3, code: 'EX-0813-01', category: '其他费用', amount: 1200, happened_at: '2026-08-13', party: '运输·张师傅', scope: '东港一号塘', basis: '人工指定', status: '待审核' },
  { id: 4, code: 'EX-0814-01', category: '人工', amount: 6000, happened_at: '2026-08-10', party: '临时工 2 人 ×3 天', scope: '全场', basis: '按工作范围', status: '已确认' },
  { id: 5, code: 'EX-0815-01', category: '其他费用', amount: 800, happened_at: '2026-08-15', party: '第三方水质检测', scope: '全场', basis: '人工指定', status: '草稿' },
]

export const assets: Asset[] = [
  { id: 1, code: 'AS-EQ-014', name: '叶轮式增氧机 1.5kW', category: '设备', value: 1800, years: 5, status: '在用', owner_scope: '东港一号塘', note: '2024-03 购入，已维护 4 次' },
  { id: 2, code: 'AS-EQ-015', name: '叶轮式增氧机 1.5kW', category: '设备', value: 1800, years: 5, status: '维修中', owner_scope: '南湾育苗塘', note: '电机轴承更换（OP-0812-04）' },
  { id: 3, code: 'AS-BL-003', name: '进排水系统改造', category: '基础建设', value: 46000, years: 10, status: '在用', owner_scope: '全场', note: '2025-11 完工验收' },
  { id: 4, code: 'AS-LS-001', name: '东港片塘租合同（2026）', category: '租赁', value: 120000, years: 1, status: '履行中', owner_scope: '东港养殖区', note: '2026-01-01 ~ 2026-12-31 · 年付' },
]

export const settlements: Settlement[] = [
  { id: 1, period: '2026-07', income: 91600, cost: 74300, profit: 17300, status: '已结算', operator: '李海宁', settled_at: '2026-08-03', note: '含 7 月饲料集中入库' },
  { id: 2, period: '2026-08（进行中）', income: 62400, cost: 58900, profit: 3500, status: '核算中', operator: '—', settled_at: '—', note: '预计 09-03 截止结算' },
]

export const templates: TemplateItem[] = [
  { id: 1, name: '塘口档案', group: '基础档案', fields: 11, updated_at: '2026-08-10' },
  { id: 2, name: '养殖批次', group: '基础档案', fields: 12, updated_at: '2026-08-10' },
  { id: 3, name: '投苗记录', group: '塘口与批次', fields: 9, updated_at: '2026-08-10' },
  { id: 4, name: '规格抽样 / 损耗 / 转塘', group: '塘口与批次', fields: 10, updated_at: '2026-08-10' },
  { id: 5, name: '喂养计划', group: '日常养殖', fields: 10, updated_at: '2026-08-12' },
  { id: 6, name: '投喂记录', group: '日常养殖', fields: 12, updated_at: '2026-08-12' },
  { id: 7, name: '日常作业记录', group: '日常养殖', fields: 8, updated_at: '2026-08-12' },
  { id: 8, name: '物料档案', group: '物料与仓储', fields: 6, updated_at: '2026-08-08' },
  { id: 9, name: '入库 / 出库 / 调拨 / 退库', group: '物料与仓储', fields: 11, updated_at: '2026-08-08' },
  { id: 10, name: '盘点 / 报损报废', group: '物料与仓储', fields: 9, updated_at: '2026-08-08' },
  { id: 11, name: '供应商档案', group: '采购与付款', fields: 7, updated_at: '2026-08-06' },
  { id: 12, name: '采购明细', group: '采购与付款', fields: 8, updated_at: '2026-08-06' },
  { id: 13, name: '客户档案', group: '销售与收款', fields: 7, updated_at: '2026-08-06' },
  { id: 14, name: '销售明细 / 出塘记录', group: '销售与收款', fields: 9, updated_at: '2026-08-06' },
  { id: 15, name: '费用与资产登记', group: '成本与经营', fields: 8, updated_at: '2026-08-14' },
]

export const importBatches: ImportBatch[] = [
  { id: 1, happened_at: '2026-08-14 10:20', data_type: '投喂记录', file_name: '投喂记录_0807-0813.xlsx', rows: 168, passed: 168, failed: 0, status: '导入成功', operator: '李海宁' },
  { id: 2, happened_at: '2026-08-12 15:40', data_type: '物料档案', file_name: '新物料清单_0812.xlsx', rows: 24, passed: 23, failed: 1, status: '整批回滚（1 行错误）', operator: '吴仓管' },
  { id: 3, happened_at: '2026-08-10 09:05', data_type: '塘口档案', file_name: '塘口扩展字段_0810.xlsx', rows: 5, passed: 5, failed: 0, status: '导入成功', operator: '李海宁' },
]

export const roleRows: RoleRow[] = [
  { id: 1, name: '超级管理员', code: 'super_admin', users: 2, summary: '全部功能 · 全场数据', data_scope: '全场', status: '启用' },
  { id: 2, name: '养殖管理员', code: 'breed_manager', users: 1, summary: '塘口 / 喂养 / 审核 / 报表', data_scope: '区域', status: '启用' },
  { id: 3, name: '养殖作业员', code: 'breed_worker', users: 2, summary: '任务执行 · 快速录入 · 领用申请', data_scope: '个人', status: '启用' },
  { id: 4, name: '仓储管理员', code: 'warehouse_manager', users: 1, summary: '物料 / 出入库 / 盘点 / 预警', data_scope: '全场（仓储）', status: '启用' },
  { id: 5, name: '采购人员', code: 'purchaser', users: 1, summary: '采购订单 / 供应商 / 应付', data_scope: '全场（采购）', status: '启用' },
  { id: 6, name: '财务人员', code: 'finance_staff', users: 0, summary: '应收应付 / 收付款 / 结算', data_scope: '全场（财务）', status: '启用' },
  { id: 7, name: '销售人员', code: 'sales_staff', users: 1, summary: '销售订单 / 客户 / 应收', data_scope: '全场（销售）', status: '启用' },
]

export const opLogs: OpLog[] = [
  { id: 1, happened_at: '2026-08-15 16:35', user: '陈志强', action: '新增', target: '投喂记录', result: '成功', detail: '东港一号塘 实际 43kg（待审核）' },
  { id: 2, happened_at: '2026-08-15 16:20', user: '吴仓管', action: '出库', target: '物料出库', result: '成功', detail: 'OUT-0815-07 · 6 袋 · 近效期优先' },
  { id: 3, happened_at: '2026-08-15 14:10', user: '李海宁', action: '审核', target: '投喂记录', result: '通过', detail: '0814 东港二号塘 13kg 异常说明合理' },
  { id: 4, happened_at: '2026-08-15 09:00', user: '吴仓管', action: '调拨', target: '仓间调拨', result: '处理中', detail: 'TF-0815-02 · 10 瓶 · 在途' },
  { id: 5, happened_at: '2026-08-14 18:02', user: '李海宁', action: '权限变更', target: '角色权限', result: '成功', detail: 'farm_worker 增加库存领用申请权限' },
  { id: 6, happened_at: '2026-08-14 08:31', user: '周敏', action: '登录', target: '会话', result: '成功', detail: '手机浏览器 · 现场作业' },
]

export const settingGroups: SettingGroup[] = [
  { group: '养殖品种', items: [{ name: '南美白对虾', value: '启用', note: '当前主养品种' }, { name: '加州鲈', value: '启用', note: '育苗试验' }, { name: '罗非鱼', value: '停用', note: '历史批次保留' }] },
  { group: '物料分类', items: [{ name: '饲料 / 渔药 / 设备配件 / 劳保工具', value: '4 类', note: '新增物料必选分类' }] },
  { group: '计量单位', items: [{ name: 'kg / 斤 / 袋 / 瓶 / 尾 / 亩', value: '6 种', note: '全局统一' }] },
  { group: '养殖区域', items: [{ name: '东港养殖区 / 南湾养殖区 / 后勤试验区', value: '3 个', note: '数据范围按区域授权' }] },
  { group: '预警参数', items: [{ name: '临期预警天数', value: '30 天', note: '修改影响库存预警生成' }, { name: '投喂偏差提醒', value: '±10%', note: '超出即生成异常提醒' }] },
]
