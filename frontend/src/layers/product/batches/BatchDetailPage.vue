<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute } from 'vue-router'
import type { BatchReconciliation, ProductionRecord } from '../../common/api/production.models'
import AppShell from '../../common/ui/AppShell.vue'
import StatusBadge from '../../common/ui/StatusBadge.vue'
import { getProductionRecord, reconcileBatch } from '../../features/production/production.service'

const route = useRoute()
const batch = ref<ProductionRecord>()
const reconciliation = ref<BatchReconciliation>()
const loading = ref(true)
const error = ref('')
const labels: Record<string, string> = { stocked: '已放养', farming: '养殖中', pending_settlement: '待结算', closed: '已关闭' }
const tones = { stocked: 'blue', farming: 'teal', pending_settlement: 'amber', closed: 'slate' } as const
const status = computed(() => String(batch.value?.batch_status ?? 'stocked'))
const number = (value: unknown) => Number(value ?? 0).toLocaleString()

onMounted(async () => {
  try {
    const id = Number(route.params.id)
    const [record, totals] = await Promise.all([getProductionRecord('batches', id), reconcileBatch(id)])
    batch.value = record.record
    reconciliation.value = totals
  } catch { error.value = '批次详情加载失败，请稍后重试' }
  finally { loading.value = false }
})
</script>

<template>
  <AppShell title="养殖批次" :breadcrumbs="['批次详情']">
    <div v-if="loading" class="page-card table-empty">正在加载批次详情…</div>
    <div v-else-if="error" class="page-card table-empty" role="alert">{{ error }}</div>
    <div v-else-if="batch && reconciliation">
      <div class="page-title">
        <div><p class="section-label">Batch detail / {{ batch.code }}</p><h1>{{ batch.name }}</h1><p>{{ batch.species }} · 塘口 ID {{ batch.pond_id }} · 数据版本 {{ batch.version }}</p></div>
        <StatusBadge :label="labels[status] ?? status" :tone="tones[status as keyof typeof tones] ?? 'slate'" />
      </div>
      <div class="detail-grid">
        <section class="page-card detail-card">
          <div class="section-head"><div><p class="section-label">Batch facts</p><h2 class="section-title">批次事实</h2></div></div>
          <dl class="detail-meta">
            <div><dt>批次编号</dt><dd>{{ batch.code }}</dd></div><div><dt>养殖品种</dt><dd>{{ batch.species }}</dd></div>
            <div><dt>初始数量</dt><dd>{{ number(batch.initial_quantity) }}</dd></div><div><dt>初始重量</dt><dd>{{ number(batch.initial_weight_kg) }} kg</dd></div>
            <div><dt>投苗时间</dt><dd>{{ batch.stocked_at || '—' }}</dd></div><div><dt>预计出塘</dt><dd>{{ batch.expected_harvest_date || '—' }}</dd></div>
          </dl>
        </section>
        <aside class="page-card detail-card" data-testid="batch-reconciliation">
          <div class="section-head"><div><p class="section-label">Stock reconciliation</p><h2 class="section-title">库存对账</h2></div><StatusBadge :label="Number(reconciliation.difference) === 0 ? '对账一致' : '存在差异'" :tone="Number(reconciliation.difference) === 0 ? 'teal' : 'rose'" /></div>
          <dl class="detail-meta"><div><dt>流水数量余额</dt><dd>{{ number(reconciliation.quantity) }}</dd></div><div><dt>流水重量余额</dt><dd>{{ number(reconciliation.weight_kg) }} kg</dd></div><div><dt>账实差异</dt><dd>{{ number(reconciliation.difference) }}</dd></div></dl>
          <p class="section-subtitle">余额仅由投苗、转入、转出、损耗、出塘及关联更正流水汇总。</p>
        </aside>
      </div>
    </div>
    <div v-else class="page-card table-empty">批次不存在或无权访问</div>
  </AppShell>
</template>
