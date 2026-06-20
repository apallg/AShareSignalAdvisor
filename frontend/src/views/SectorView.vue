<template>
  <div>
    <h1 class="page-title">板块选股</h1>
    <div class="flex mb-2">
      <select v-model="sector" style="flex:1;padding:8px 14px;border:1px solid #ddd;border-radius:6px;font-size:14px;">
        <option value="">-- 选择板块 --</option>
        <option v-for="s in sectors" :key="s" :value="s">{{ s }}</option>
      </select>
      <button class="btn" @click="search">查询板块</button>
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <LoadingSpinner v-if="loading" />
    <DataTable
      v-if="stocks.length"
      :rows="sorted"
      :columns="columns"
      :title="sector + ' - 成分股'"
      :count="stocks.length"
      row-key="code"
    >
      <template #cell-code="{ row }">{{ row.code || row['代码'] }}</template>
      <template #cell-name="{ row }">{{ row.name || row['名称'] }}</template>
      <template #cell-price="{ row }">{{ row.price || row['最新价'] || '--' }}</template>
      <template #cell-pct_chg="{ row }">
        <span :class="(row['涨跌幅'] || row.pct_chg || 0) >= 0 ? 'text-red' : 'text-green'">
          {{ row['涨跌幅'] || row.pct_chg || '--' }}
        </span>
      </template>
      <template #cell-volume="{ row }">{{ row.volume || row['成交量'] || '--' }}</template>
    </DataTable>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api/index.js'
import DataTable from '../components/DataTable.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'

const sectors = ref([])
const sector = ref('')
const stocks = ref([])
const loading = ref(false)
const error = ref('')

const columns = [
  { key: 'code', label: '代码' },
  { key: 'name', label: '名称' },
  { key: 'price', label: '最新价' },
  { key: 'pct_chg', label: '涨跌幅' },
  { key: 'volume', label: '成交量' },
]

const sorted = computed(() =>
  [...stocks.value].sort((a, b) => (b['涨跌幅'] || b.pct_chg || 0) - (a['涨跌幅'] || a.pct_chg || 0))
)

onMounted(async () => {
  try {
    const r = await api.get('/sectors/list')
    sectors.value = (r.data || []).map(s => s['板块名称'] || s.board_name || s.name)
  } catch (e) { error.value = e.message }
})

async function search() {
  if (!sector.value) return
  loading.value = true; error.value = ''; stocks.value = []
  try {
    const r = await api.get('/sectors/' + encodeURIComponent(sector.value) + '/stocks')
    stocks.value = r.data || []
    if (!stocks.value.length) error.value = '无数据'
  } catch (e) { error.value = e.message }
  finally { loading.value = false }
}
</script>
