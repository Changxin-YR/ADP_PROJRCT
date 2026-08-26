<script setup lang="ts">
import type { CostStructure } from '../../common/api/cost.models'
import AppIcon from '../../common/ui/AppIcon.vue'
import { formatMoney, formatShare } from './cost-page.helpers'

const props = defineProps<{ structure: CostStructure }>()
const weight = () => `${Number(props.structure.confirmed_output_weight_jin).toLocaleString('zh-CN', { minimumFractionDigits: 3 })} 斤`
</script>

<template>
  <section class="kpi-grid cost-kpi-grid" aria-label="成本指标">
    <article class="page-card kpi-card">
      <div class="kpi-card__top"><span>期间总成本</span><span class="kpi-card__icon"><AppIcon name="money" :size="15" /></span></div>
      <strong data-testid="cost-total">{{ formatMoney(structure.total_amount) }}</strong>
      <small>费用 {{ structure.source_fact_counts.expense }} · 资产 {{ structure.source_fact_counts.asset }} · 仓储 {{ structure.source_fact_counts.warehouse }}</small>
    </article>
    <article class="page-card kpi-card">
      <div class="kpi-card__top"><span>已确认收入</span><span class="kpi-card__icon"><AppIcon name="trend" :size="15" /></span></div>
      <strong data-testid="cost-income">{{ formatMoney(structure.confirmed_income_amount) }}</strong>
      <small>{{ structure.source_fact_counts.sales }} 笔已核验销售交付</small>
    </article>
    <article class="page-card kpi-card" :class="Number(structure.confirmed_profit_amount) >= 0 ? 'kpi--teal' : 'kpi--rose'">
      <div class="kpi-card__top"><span>期间确认利润</span><span class="kpi-card__icon"><AppIcon name="calculator" :size="15" /></span></div>
      <strong data-testid="cost-profit">{{ formatMoney(structure.confirmed_profit_amount) }}</strong>
      <small>已确认收入减已确认成本</small>
    </article>
    <article class="page-card kpi-card">
      <div class="kpi-card__top"><span>直接成本占比</span><span class="kpi-card__icon kpi-card__icon--amber"><AppIcon name="trend" :size="15" /></span></div>
      <strong data-testid="cost-direct-share">{{ formatShare(structure.direct_share) }}</strong>
      <small>{{ formatMoney(structure.direct_amount) }} · 苗种、饲料、动保</small>
    </article>
    <article class="page-card kpi-card">
      <div class="kpi-card__top"><span>公共成本占比</span><span class="kpi-card__icon"><AppIcon name="layers" :size="15" /></span></div>
      <strong data-testid="cost-public-share">{{ formatShare(structure.public_share) }}</strong>
      <small>{{ formatMoney(structure.public_amount) }} · 按规则分摊</small>
    </article>
    <article class="page-card kpi-card kpi--teal">
      <div class="kpi-card__top"><span>单位产量成本</span><span class="kpi-card__icon"><AppIcon name="calculator" :size="15" /></span></div>
      <strong data-testid="cost-unit-cost">{{ structure.unit_production_cost ? `${structure.unit_production_cost} 元/斤` : '待接入产量' }}</strong>
      <small>{{ structure.unit_cost_status === 'available' ? `${weight()} · ${structure.source_fact_counts.production} 笔产出` : '当前不使用估算存塘量替代真实产量' }}</small>
    </article>
  </section>
</template>

<style scoped>
.cost-kpi-grid{grid-template-columns:repeat(3,minmax(0,1fr))}.kpi-card::after{display:none}.kpi-card__icon--amber{color:#b97735;background:#fff4e7}@media(max-width:900px){.cost-kpi-grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:560px){.cost-kpi-grid{grid-template-columns:1fr}}
</style>
