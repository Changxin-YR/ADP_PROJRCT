# ADP 手工验收数据清单（含本轮新增闭环）

> 数据前缀统一 **MT2609-**，便于测试后一键识别与清理。
> 本轮新打通：请购闭环、退货闭环、存塘量来自生产事实、成本防重复归集 + 旧入口锁账、批次生命周期入口。

---

## 0. 环境与账号

| 检查项 | 操作 | 通过标准 |
| --- | --- | --- |
| 后端健康 | 打开 /api/v1/health | code=OK，data.environment 有值 |
| 前端 | 打开 / 或 /login | 正常渲染，控制台无红错 |
| 同源代理 | 登录 | 请求为 /api/v1/auth/login，不是 http://127.0.0.1:5001 |
| CSRF | 刷新登录页 | 有 GET /api/v1/auth/csrf 返回 200 |

本地启动（PowerShell）：

    $env:FLASK_APP = "backend.app:app"; python -m flask run --host 127.0.0.1 --port 5001
    cd frontend; npm run dev            # 5173，/api 代理到 5001

两个账号：A 写入（超管）、B 核验。系统强制"经办人 != 核验人"。
核验权限按角色拆（warehouse.verify 超管/仓管；finance.payment.verify、cost.entry.confirm 超管/财务）。
一次跑通全模块建议两个账号都用超管；验角色隔离时再用对应角色，跨模块 403 属正确行为。

自动验收（推荐先跑）：

    python -m scripts.manual_test_flow --base-url http://127.0.0.1:5001 `
      --writer-id 写入账号 --writer-password '密码' `
      --verifier-id 核验账号 --verifier-password '密码'

---

## 1. 塘口主数据

| 步骤 | 关键字段 |
| --- | --- |
| 1-A 区域 | 编码 MT2609-AREA-N，名称 [验收]北区测试基地（已有北区/南区可跳过） |
| 1-B 分组 | 所属区域=已核验北区；编码 MT2609-GRP-01；名称 [验收]北区成鱼塘组 |
| 1-C 1号塘 | MT2609-POND-01；[验收]北区1号塘；区域 北区；分组 GRP-01；草鱼；42.5 亩；增氧机 3；投苗规格 100 尾/斤；当前规格 待投苗；存塘量 0；来源 manual；初始状态 筹建 build |
| 1-D 2号塘 | MT2609-POND-02；38 亩；增氧机 2；其余同上 |

每条走 草稿 -> 提交 -> 换人核验。
反向：面积 0/负 -> 400；增氧机 1.5 -> 前端拦截；新建即选"养殖中" -> 400 POND_STATUS_INVALID；
重复编码 -> 唯一键提示而非 500；不存在的分组 ID -> 400 MASTER_RELATION_NOT_FOUND。

塘口状态流转（1号塘）：build -> stocked -> farming -> rest/clean -> rebuild，走「申请 + 换人核验」。
反向：A 提交后 A 自己核验 -> 403 SELF_APPROVAL_FORBIDDEN；直接 PATCH 带 pond_status -> 409 POND_STATUS_CHANGE_REQUIRES_REVIEW；
已核验塘口编辑 -> 409 RECORD_READ_ONLY；仍有存塘时申请 rest/clean -> 409 POND_STATUS_STOCK_REMAINING。

---

## 2. 业务主数据

| 对象 | 关键字段 |
| --- | --- |
| 供应商 MT2609-SUP-01 | [验收]湖州水产物资有限公司，王建国，0572-2388666，账期 30，额度 200000 |
| 物料 MT2609-MAT-FEED | [验收]草鱼膨化饲料，饲料，40kg/袋，kg，安全库存 500，保质期 180 |
| 物料 MT2609-MAT-SEED | [验收]草鱼苗种，苗种，100尾/斤，尾 |
| 物料 MT2609-MAT-HEALTH | [验收]聚维酮碘，动保，500ml/瓶，瓶，安全库存 10，540 天 |
| 仓库 MT2609-WH-01 | [验收]综合一号仓，默认基地，北区，启用 |
| 客户 MT2609-CUS-01 | [验收]杭州鲜活水产批发，李美娟，0571-88661234，账期 15，额度 150000 |

只有已核验的供应商/物料/客户才会进入采购、销售、仓储下拉 —— 这是"主数据 -> 业务单据"的关键一环。

---

## 3. 养殖批次

MT2609-BATCH-01；[验收]草鱼 2026 秋批次；初始塘口 1号塘；草鱼；初始 20000 尾 / 1600 kg；
投苗时间 今天 08:00（不得晚于当前）；预计出塘 今天+90；状态 stocked。

链路：创建 -> 提交 -> 换人核验 -> 当前存量自动入账 20000 / 1600，对账显示"对账一致"。
反向：数量与重量都为 0 -> 400 PRODUCTION_QUANTITY_REQUIRED；出塘日早于放苗日 / 投苗时间在未来 -> 400 PRODUCTION_DATE_INVALID；
新建即 closed -> 400 PRODUCTION_BATCH_STATUS_INVALID。

新：批次生命周期入口（stocked -> farming -> pending_settlement -> closed，每次必须填原因）
- 仍有存塘量改 closed -> 409 BATCH_STOCK_NOT_ZERO（前端必须原样展示后端中文原因）
- 有未完成生产单据改 pending_settlement -> 409 BATCH_OPEN_WORK
- 非法跳级 -> 409 INVALID_BATCH_STATUS_TRANSITION

新：塘口存塘量来自生产事实（GET /api/v1/production/ponds/{id}/stock-summary，列表版 /ponds/stock-summary?pond_ids=）
- 「存塘量（批次流水）」只读；档案手工值仅标注"仅供参考"
- 两者不一致时出现克制提示（不是红色报错）
- 展示批次分布（各批次数量/重量/状态）与最近抽样（时间、样本数量、样本重量、折算平均体重）
- 无批次流水 -> data_source=manual 回落手工值；都没有 -> none

---

## 4. 日常养殖

作业（类型化参数，缺一即 400 DAILY_OP_PARAM_REQUIRED）：

| 单号 | 类型 | 关键参数 |
| --- | --- | --- |
| MT2609-OP-01 | patrol | operation_type=patrol，source_detail 含 water_quality 与 fish_activity |
| MT2609-OP-02 | water_quality | temperature_c=28.5，ph=7.6（0-14），dissolved_oxygen_mg_l=5.2 |
| MT2609-OP-03 | water_change | volume_m3=120，water_source=北区东渠 |

- 抽样：MT2609-SP-01（50 尾 / 6.5kg）、MT2609-SP-02（50 尾 / 8.0kg）
- 转塘 MT2609-TR-01：1号塘 -> 2号塘，5000 尾 / 400kg；来源=目标 -> 400；核验缺凭据 -> 400 EVIDENCE_REQUIRED；核验后双向流水等量反向
- 损耗 MT2609-LS-01：疾病损耗，300 尾 / 25kg，原因必填，核验带凭据

---

## 5. 采购 -> 收货 -> 应付 -> 付款

1. 采购单 MT2609-PO-01：SUP-01 / MAT-FEED / WH-01，200 kg x 12.5，到货 今天，到期 今天+30（不得早于到货日）
   反向：A 审批自己提交的单 -> 403 SELF_APPROVAL_FORBIDDEN；数量 0 -> 400 PURCHASE_AMOUNT_INVALID
2. 入库 MT2609-IN-01：200，单位成本 12.5，批次 MT2609-LOT-FEED-01，生产日 今天-10，到期 今天+170（生产日不得晚于到期日），来源 PO-01
   反向：不带凭据核验 -> 400 EVIDENCE_REQUIRED
   核验后：台账 +200；自动生成应付 2500（重复核验不生成第二笔）
3. 付款 MT2609-PAY-01：1500，银行转账，核验带凭据 -> 余额 2500 -> 1000（partial）
   反向：超过余额 -> 拒绝；核验后「冲销」-> 余额回升、原付款保留

新：库存预警 -> 请购单 -> 采购单
1. 库存预警对低库存物料点处理 -> 选「补货」-> 可关联请购单（新）或采购单（老行为兼容）；预警行新增 suggested_quantity 可直接预填
2. 请购单 MT2609-REQ-01：MAT-FEED，300，WH-01，原因必填
3. draft -> submit -> approve（换人）-> convert
   - 经办人自审 -> 403 SELF_APPROVAL_FORBIDDEN
   - draft 直接 convert -> 409 INVALID_STATE_TRANSITION
   - 缺 supplier_id/unit_price/due_date 任一 -> 400 PURCHASE_REQUISITION_CONVERT_FIELDS
   - 重复 convert -> 409 PURCHASE_REQUISITION_ALREADY_CONVERTED，且不得多建第二张采购单
   - convert 返回体是 {"data":{"record":采购单,"requisition":请购单}}（不是单 record 包装）
   - 采购单回填 requisition_id，列表可见 requisition_code
   - 已知待产品决策：请购单号与采购单号共用编码空间，撞号文案语义偏"已转换"

---

## 6. 出塘 -> 销售 -> 应收 -> 收款

1. 出塘 MT2609-HV-01：批次1，1号塘，3000 尾 / 450kg，核验带凭据 -> 批次存量减少
2. 销售单 MT2609-SO-01：CUS-01，塘口 1号塘，批次1，草鱼，450 kg，单位 kg（仅 kg/jin/tail），16.80，销售 今天，到期 今天+15（不得早于销售日），换人审批
3. 交付 MT2609-DLV-01：来源 SO-01，已核验出塘单 HV-01，450，交付时间 今天
   反向：数量 > 销售数量 -> 拒绝；核验缺凭据 -> 400 EVIDENCE_REQUIRED；同一出塘单被两张交付单认领 -> 拒绝
   核验后自动生成应收 7560
4. 收款 MT2609-RCP-01：全额 7560，核验带凭据 -> 应收余额 0（settled）

新：退货闭环
- 菜单：采购与付款 -> 供应商退货；销售与收款 -> 客户退货（与「物料与仓储 -> 退库管理」不是同一业务）
- 供应商退货 MT2609-PRET-01：来源=已核验入库单 IN-01，数量 20，原因必填
  - amount 由后端按 数量 x 来源入库单价 计算，表单不填；payable_id 后端带出
  - warehouse_id / material_id / inventory_lot_id 由所选入库单自动带出（手填必然 RETURN_SOURCE_INVALID）
  - draft -> submit -> verify -> 冲减应付 250、退回库存 20
- 客户退货 MT2609-SRET-01：来源=已核验交付单 DLV-01，数量 20，退款金额 <= 退货金额 -> 冲减应收
- 反向：来源未核验 -> 409 RETURN_SOURCE_INVALID；退款 > 退货金额 -> 400 RETURN_REFUND_INVALID；数量 <= 0 -> 400 RETURN_QUANTITY_INVALID
- 退货接口无 PATCH，页面刻意不提供"编辑"，只有 新建/提交/核验/取消/删除草稿

---

## 7. 费用 / 资产 / 分摊 / 结算

费用（均需 提交 -> 换人核验（带凭据）-> 确认入账（带凭据））：

| 单号 | 类别 | 金额 | 性质 | 归属 |
| --- | --- | --- | --- | --- |
| MT2609-EXP-01 | labor | 18000.00 | public | 留空 |
| MT2609-EXP-02 | electricity | 6200.50 | public | 留空 |
| MT2609-EXP-03 | other | 2500.00 | direct | pond + 1号塘 ID |

期间：开始=本月1日，结束=今天；发生日必须在期间内（400 COST_PERIOD_INVALID）；金额 > 0 且最多两位小数。

新：成本防重复归集
库存出库核验会自动生成 source_type=warehouse_ledger 的成本条目。因此手工费用满足
「manual_expense + 类别属于 {饲料, 苗种, 动保} + 归属塘口/批次 + 与自动成本期间重叠」时必须被拒绝：
409 COST_SOURCE_DUPLICATED；显式改用 manual_feed_offset 或 manual_feed_direct 可放行。
验证前提：先做一次领料出库并核验，再登记同塘口同期间的饲料类手工费用。

资产 MT2609-AST-01：[验收]1.5kW 增氧机，equipment，购买日 今天-20，原值 4800，残值 200（小于原值），
期限 60 月，折旧开始 今天-19（不早于购买日）-> 提交 -> 核验 -> 确认。

分摊：期间 + 基地必填 -> 来源合计 = 已分摊合计；期间开始 > 结束 -> 400 COST_PERIOD_INVALID；不选基地 -> 400 COST_ALLOCATION_SCOPE_REQUIRED。
结算 MT2609 期间结算：保存 -> 提交 -> 换人核验 -> 确认锁定（自审 403）-> 可反结算（原因 >= 2 字）。

新：锁账一致性 —— 两个成本入口都要测
期间确认结算后补写成本必须被拒绝：
- 新入口 POST /api/v1/cost/expenses -> 409 COST_PERIOD_LOCKED
- 旧入口 POST /api/v1/cost/entries（费用登记页所走的路）同样必须 409（旧入口此前没有该校验，是本次修复点）

---

## 8. 待办、审计与安全边界

- A 提交单据 -> B 的工作台出现开放待办；B 完成核验后该待办消失并进入历史
- PATCH /api/v1/work-items/{id} 直接完成领域待办 -> 必须被拒绝
- 操作日志（超管）含 request_id 与前后值且无删除入口；非超管 -> 403

| 场景 | 期望 |
| --- | --- |
| 自审（主数据/生产/仓储/采购/销售/成本） | 403 SELF_APPROVAL_FORBIDDEN |
| 旧 expected_version | 409 VERSION_CONFLICT |
| 已核验记录 PATCH | 409 RECORD_READ_ONLY |
| 已提交/已核验记录 DELETE | 409 DELETE_NOT_ALLOWED |
| 请求体带 status/row_version 等保留字段 | 400 相应 FIELD_INVALID |
| 跨数据范围 | 列表静默过滤；单条 get/approve -> 403 DATA_SCOPE_FORBIDDEN |
| 连点保存 / 断网重提 | 只产生一条记录（前端去重 + Idempotency-Key） |
| 高风险单据核验缺凭据 | 400 EVIDENCE_REQUIRED |

---

## 9. 数据闭环核对

| 检查项 | 期望 |
| --- | --- |
| 塘口 | 2 口，1 号塘 farming；存塘量显示来自批次流水 |
| 批次 | 20000/1600 减 转塘 5000/400 减 损耗 300/25 减 出塘 3000/450（加减退货/更正）；对账差异 = 0 |
| 库存 | 入库 +200；台账全为追加式流水；退货后与台账一致 |
| 应付 | 2500 -> 付款 1500 -> 退货冲减 250；余额与状态自洽 |
| 应收 | 7560 -> 收款 7560 -> 客户退货冲减；余额与状态自洽 |
| 采购来源 | REQ-01 为 converted，采购单回填 requisition_id |
| 成本 | 九类归集 = 已确认费用 + 折旧 + 库存自动成本；无重复归集 |
| 分摊/结算 | 来源合计 = 分摊明细合计；锁定后新旧入口均拒绝补写 |
| 待办/审计/附件 | 无遗留开放待办；写操作有审计；凭据 SHA-256 与库内一致 |

---

## 10. 本轮改造点速查

| 改造 | 验证入口 | 关键期望 |
| --- | --- | --- |
| 请购闭环 | 库存预警 -> 补货；/api/v1/purchase/requisitions | 预警可引请购；重复 convert 409 且不多建单 |
| 退货闭环 | 菜单「供应商退货」「客户退货」 | 冲减应付/应收 + 退回库存；无"编辑" |
| 存塘量事实化 | 塘口详情/列表 | 来自批次流水；手工值兜底并提示差异 |
| 批次生命周期 | 批次详情/列表 | 只允许合法下一状态；存活体/未完成单据时拒绝并显示原因 |
| 成本防重复 | 费用登记（饲料类 + 塘口 + 重叠期间） | 409 COST_SOURCE_DUPLICATED；白名单来源放行 |
| 锁账统一 | 结算确认后分别打新/旧成本入口 | 两者均 409 COST_PERIOD_LOCKED |
