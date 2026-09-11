/**
 * 演示范围（Demo scope）：把"面试演示"关心的主线与完整系统解耦。
 *
 * - 默认（未设置 VITE_DEMO_SCOPE）为完整档：九个业务分区全部可见。
 * - 设置 VITE_DEMO_SCOPE=core 为核心档：面向 AI 全栈演示。
 *
 * 核心档的取舍依据：对话入口 AgentPanel 是**全局浮层**（任何页面都在），
 * 所以核心档要留的不是"业务菜单最多的那几页"，而是"智能体说得清、也做得动、且能当场核验"的数据面：
 * 塘口/批次存量、出塘事实、销售与应收、成本构成与期间结算。
 *
 * 设计取舍刻意写在这里而不是删代码：核心档隐藏的分区（日常养殖、物料仓储、采购付款、
 * 数据交换、系统管理）在完整档下仍然可用，且后端接口与测试都不受影响。
 */
import type { NavGroup, NavItem } from './navigation'

/** 核心档保留的分区 code（与 navigation.ts 的 NavGroup.code 对应）。 */
export const CORE_GROUP_CODES = ['ponds-batches', 'sales', 'cost'] as const

/**
 * 核心档保留的页面 ="AI 说得清、也做得动"的骨架：
 * 对话入口（AgentPanel）是全局浮层，本列表是供它查询/落库的**数据面**，
 * 用来当场核验智能体的回答是否等于真实业务事实。
 */
export const CORE_ITEM_PATHS = [
  '/ponds',             // 核验"某塘口存塘量/规格"的回答是否等于批次流水汇总
  '/pond-groups',       // 分组口径
  '/batches',           // 核验"某批次还剩多少"的回答
  '/harvests',          // 出塘事实（销售交付的来源）
  '/sales/orders',      // 销售 + 交付
  '/sales/receivables', // 核验"客户还欠多少"的回答
  '/cost/structure',    // 成本构成（分摊结果落点）
  '/cost/settlements',  // 期间结算（写操作确认的典型场景）
] as const

export function isCoreScope(): boolean {
  const raw = String(import.meta.env.VITE_DEMO_SCOPE ?? '').trim().toLowerCase()
  return raw === 'core'
}

export function isCoreGroup(group: NavGroup): boolean {
  return (CORE_GROUP_CODES as readonly string[]).includes(group.code)
}

export function isCoreItem(item: NavItem): boolean {
  return (CORE_ITEM_PATHS as readonly string[]).includes(item.to)
}
