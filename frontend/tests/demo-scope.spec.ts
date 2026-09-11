import { afterEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'

import { createSessionStore } from '../src/layers/common/session/session.store'
import AppShell from '../src/layers/common/ui/AppShell.vue'
import { CORE_GROUP_CODES, CORE_ITEM_PATHS, isCoreGroup, isCoreItem } from '../src/layers/common/ui/app-shell/demoScope'
import { navGroups } from '../src/layers/common/ui/app-shell/navigation'

function testRouter() {
  return createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/workbench', component: { template: '<div />' } },
      { path: '/:pathMatch(.*)*', component: { template: '<div />' } },
    ],
  })
}

function signIn() {
  createSessionStore().setUser({
    id: 1,
    phone: '13800000000',
    name: '企业管理员',
    status: 'active',
    roles: [{ id: 1, code: 'super_admin', name: '超级管理员' }],
    data_scopes: [],
    permissions: [
      'workbench.enter', 'work_item.view', 'master_data.view', 'production.view',
      'warehouse.view', 'purchase.view', 'sales.view', 'cost.view', 'data_exchange.view',
      'finance.receivable.view', 'finance.payable.view',
      'auth.user.manage', 'auth.role.manage', 'audit.view',
    ],
  })
}

async function renderShell() {
  const router = testRouter()
  await router.push('/workbench')
  await router.isReady()
  return mount(AppShell, { global: { plugins: [router], stubs: { Teleport: true } } })
}

afterEach(() => {
  vi.unstubAllEnvs()
  vi.restoreAllMocks()
})

describe('demo scope', () => {
  it('完整档：九个分区全部可见（不设 VITE_DEMO_SCOPE）', async () => {
    signIn()
    const wrapper = await renderShell()
    const text = wrapper.text()
    expect(text).toContain('塘口与批次')
    expect(text).toContain('日常养殖')
    expect(text).toContain('物料与仓储')
    expect(text).toContain('系统管理')
    expect(navGroups.filter(isCoreGroup)).toHaveLength(3)
  })

  it('核心档：只保留主线分区与主线页面', async () => {
    vi.stubEnv('VITE_DEMO_SCOPE', 'core')
    signIn()
    const wrapper = await renderShell()
    const text = wrapper.text()

    // 主线：塘口档案 / 塘口分组 / 养殖批次 / 出塘捕捞 / 销售明细 / 应收账款 / 成本构成 / 期间结算
    for (const label of ['塘口与批次', '塘口档案', '塘口分组', '养殖批次', '出塘捕捞', '销售与收款', '销售明细', '应收账款', '成本与经营', '成本构成', '期间结算']) {
      expect(text, `核心档应包含 ${label}`).toContain(label)
    }

    // 已裁剪：非主线分区与页面不应出现
    for (const label of ['日常养殖', '物料与仓储', '采购与付款', '数据交换', '系统管理', '规格抽样', '转塘记录', '损耗记录', '供应商退货', '客户退货', '费用登记', '资产台账', '仓储台账']) {
      expect(text, `核心档不应包含 ${label}`).not.toContain(label)
    }
  })

  it('核心档的取舍是可断言的纯函数（不依赖渲染）', () => {
    const groups = navGroups.filter(isCoreGroup).map((group) => group.code)
    expect(groups).toEqual([...CORE_GROUP_CODES])
    expect(CORE_ITEM_PATHS.every((path) => path.startsWith('/'))).toBe(true)
    const coreItems = navGroups.flatMap((group) => group.items).filter(isCoreItem).map((item) => item.to)
    expect(coreItems).toEqual([...CORE_ITEM_PATHS])
  })
})
