import { createRouter, createWebHistory } from 'vue-router'
import { createApiClient } from './layers/common/api/client'
import { createSessionStore } from './layers/common/session/session.store'
import { hasPermission } from './layers/common/security/access-control'

const auth = { authOnly: true, activeOnly: true, requiredStatus: 'active' }

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/auth/login' },
    { path: '/auth/login', component: () => import('./layers/product/auth/LoginPage.vue'), meta: { guestOnly: true } },
    { path: '/auth/register', component: () => import('./layers/product/auth/RegisterPage.vue'), meta: { guestOnly: true } },
    { path: '/auth/pending', component: () => import('./layers/product/auth/PendingPage.vue'), meta: { authOnly: true } },
    { path: '/auth/rejected', component: () => import('./layers/product/auth/RejectedPage.vue'), meta: { authOnly: true } },
    { path: '/auth/first-password', component: () => import('./layers/product/auth/PasswordChangePage.vue'), meta: { authOnly: true, mode: 'first-login' } },
    { path: '/auth/password-change', component: () => import('./layers/product/auth/PasswordChangePage.vue'), meta: { authOnly: true, mode: 'self-service' } },

    // 工作台与协作
    { path: '/workbench', component: () => import('./layers/product/workbench/WorkbenchDashboardPage.vue'), meta: { ...auth, requiredPermission: 'workbench.enter' } },
    { path: '/messages', component: () => import('./layers/product/workbench/QueuePage.vue'), props: { mode: 'messages' }, meta: { ...auth, requiredPermission: 'work_item.view' } },
    { path: '/todos', component: () => import('./layers/product/workbench/QueuePage.vue'), props: { mode: 'todos' }, meta: { ...auth, requiredPermission: 'work_item.view' } },

    // 塘口与批次
    { path: '/ponds', component: () => import('./layers/product/ponds/PondListPage.vue'), meta: { ...auth, requiredPermission: 'master_data.view' } },
    { path: '/ponds/:id', component: () => import('./layers/product/ponds/PondDetailPage.vue'), meta: { ...auth, requiredPermission: 'master_data.view' } },
    { path: '/pond-groups', component: () => import('./layers/product/pond-groups/PondGroupPage.vue'), meta: { ...auth, requiredPermission: 'master_data.view' } },
    { path: '/batches', component: () => import('./layers/product/batches/BatchListPage.vue'), meta: { ...auth, requiredPermission: 'production.view' } },
    { path: '/batches/:id', component: () => import('./layers/product/batches/BatchDetailPage.vue'), meta: { ...auth, requiredPermission: 'production.view' } },
    { path: '/sampling', component: () => import('./layers/product/ponds-batches/SamplingPage.vue'), meta: { ...auth, requiredPermission: 'production.view' } },
    { path: '/transfers', component: () => import('./layers/product/ponds-batches/TransferPage.vue'), meta: { ...auth, requiredPermission: 'production.view' } },
    { path: '/losses', component: () => import('./layers/product/ponds-batches/LossPage.vue'), meta: { ...auth, requiredPermission: 'production.view' } },
    { path: '/harvests', component: () => import('./layers/product/ponds-batches/HarvestPage.vue'), meta: { ...auth, requiredPermission: 'production.view' } },

    // 日常养殖
    { path: '/feeding/plans', component: () => import('./layers/product/daily-farming/FeedPlanPage.vue'), meta: { ...auth, requiredPermission: 'production.view' } },
    { path: '/feeding/tasks', component: () => import('./layers/product/daily-farming/FeedTaskPage.vue'), meta: { ...auth, requiredPermission: 'production.view' } },
    { path: '/feeding/logs', component: () => import('./layers/product/daily-farming/FeedLogPage.vue'), meta: { ...auth, requiredPermission: 'production.view' } },
    { path: '/daily-ops', component: () => import('./layers/product/daily-farming/DailyOpsPage.vue'), meta: { ...auth, requiredPermission: 'production.view' } },

    // 物料与仓储
    { path: '/warehouse/materials', component: () => import('./layers/product/warehouse/MaterialPage.vue'), meta: { ...auth, requiredPermission: 'warehouse.view' } },
    { path: '/warehouse/in', component: () => import('./layers/product/warehouse/StockInPage.vue'), meta: { ...auth, requiredPermission: 'warehouse.view' } },
    { path: '/warehouse/out', component: () => import('./layers/product/warehouse/StockOutPage.vue'), meta: { ...auth, requiredPermission: 'warehouse.view' } },
    { path: '/warehouse/returns', component: () => import('./layers/product/warehouse/StockReturnPage.vue'), meta: { ...auth, requiredPermission: 'warehouse.view' } },
    { path: '/warehouse/transfers', component: () => import('./layers/product/warehouse/StockTransferPage.vue'), meta: { ...auth, requiredPermission: 'warehouse.view' } },
    { path: '/warehouse/stocktakes', component: () => import('./layers/product/warehouse/StocktakePage.vue'), meta: { ...auth, requiredPermission: 'warehouse.view' } },
    { path: '/warehouse/scraps', component: () => import('./layers/product/warehouse/ScrapPage.vue'), meta: { ...auth, requiredPermission: 'warehouse.view' } },
    { path: '/warehouse/alerts', component: () => import('./layers/product/warehouse/StockAlertPage.vue'), meta: { ...auth, requiredPermission: 'warehouse.view' } },
    { path: '/warehouse/ledger', component: () => import('./layers/product/warehouse/StockLedgerPage.vue'), meta: { ...auth, requiredPermission: 'warehouse.view' } },

    // 采购与付款
    { path: '/purchase/suppliers', component: () => import('./layers/product/purchase/SupplierPage.vue'), meta: { ...auth, requiredPermission: 'purchase.view' } },
    { path: '/purchase/orders', component: () => import('./layers/product/purchase/PurchasePage.vue'), meta: { ...auth, requiredPermission: 'purchase.view' } },
    { path: '/purchase/payables', component: () => import('./layers/product/purchase/PayablePage.vue'), meta: { ...auth, requiredPermission: 'finance.payable.view' } },

    // 销售与收款
    { path: '/sales/customers', component: () => import('./layers/product/sales/CustomerPage.vue'), meta: { ...auth, requiredPermission: 'sales.view' } },
    { path: '/sales/orders', component: () => import('./layers/product/sales/SalePage.vue'), meta: { ...auth, requiredPermission: 'sales.view' } },
    { path: '/sales/receivables', component: () => import('./layers/product/sales/ReceivablePage.vue'), meta: { ...auth, requiredPermission: 'finance.receivable.view' } },

    // 成本与经营
    { path: '/cost/structure', component: () => import('./layers/product/cost/CostPage.vue'), meta: { ...auth, requiredPermission: 'cost.view' } },
    { path: '/cost/expenses', component: () => import('./layers/product/cost/ExpensePage.vue'), meta: { ...auth, requiredPermission: 'cost.view' } },
    { path: '/cost/assets', component: () => import('./layers/product/cost/AssetPage.vue'), meta: { ...auth, requiredPermission: 'cost.view' } },
    { path: '/cost/settlements', component: () => import('./layers/product/cost/SettlementPage.vue'), meta: { ...auth, requiredPermission: 'cost.view' } },

    // 数据交换
    { path: '/data/templates', component: () => import('./layers/product/data/TemplatePage.vue'), meta: { ...auth, requiredPermission: 'data_exchange.view' } },
    { path: '/data/imports', component: () => import('./layers/product/data/ImportPage.vue'), meta: { ...auth, requiredPermission: 'data_exchange.view' } },

    // 系统管理
    { path: '/admin/users', component: () => import('./layers/product/admin/UserManagementPage.vue'), meta: { ...auth, requiredPermission: 'auth.user.manage' } },
    { path: '/admin/applications', component: () => import('./layers/product/admin/AccountReviewPage.vue'), meta: { ...auth, requiredPermission: 'auth.review' } },
    { path: '/admin/roles', component: () => import('./layers/product/admin/RolePage.vue'), meta: { ...auth, requiredPermission: 'auth.role.manage' } },
    { path: '/admin/logs', component: () => import('./layers/product/admin/OpLogPage.vue'), meta: { ...auth, requiredPermission: 'audit.view' } },
    { path: '/admin/settings', component: () => import('./layers/product/admin/SettingPage.vue'), meta: { ...auth, requiredPermission: 'auth.user.manage' } },
  ],
})

const api = createApiClient()
const session = createSessionStore()

router.beforeEach(async (to) => {
  const needsUser = Boolean(to.meta.authOnly || to.meta.guestOnly)
  if (!needsUser) return true
  const user = session.user.value ?? await session.load(api)
  if (to.meta.guestOnly && user) return session.nextPath.value
  if (to.meta.authOnly && !user) return { path: '/auth/login', query: { redirect: to.fullPath } }
  if ((to.meta.activeOnly || to.meta.requiredStatus === 'active') && user?.status !== 'active') return session.nextPath.value
  const requiredPermission = typeof to.meta.requiredPermission === 'string' ? to.meta.requiredPermission : null
  if (requiredPermission && !hasPermission(user, requiredPermission)) return session.nextPath.value
  return true
})
