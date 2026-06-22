<template>
  <div>
    <h1 class="page-title">板块选股</h1>
    <div class="flex mb-2" style="gap:8px;">
      <select v-model="sector" style="flex:1;padding:8px 14px;border:1px solid #ddd;border-radius:6px;font-size:14px;">
        <option value="">-- 选择板块 --</option>
        <option v-for="s in sectors" :key="s" :value="s">{{ s }}</option>
      </select>
      <button class="btn" @click="search">查询成分股</button>
      <button class="btn" style="background:#e94560;" @click="scanSR" :disabled="sRLoading">
        {{ sRLoading ? '扫描中...' : '扫描支撑/压力位' }}
      </button>
    </div>
    <div v-if="error" class="error">{{ error }}</div>
    <LoadingSpinner v-if="loading" />

    <!-- 成分股列表 -->
    <DataTable
      v-if="stocks.length"
      :rows="sortedStocks"
      :columns="stockColumns"
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

    <!-- 支撑/压力位扫描结果 -->
    <div v-if="srResults.length" class="card" style="margin-top:16px;">
      <div class="card-title">
        支撑/压力位扫描结果 ({{ srResults.length }} 只)
        <span style="font-weight:normal;font-size:12px;color:#999;margin-left:8px;">
          离支撑/压力位 &lt;3% 视为接近
        </span>
      </div>
      <table>
        <thead>
          <tr>
            <th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th>
            <th>支撑类型</th><th>支撑价</th><th>距支撑</th>
            <th>压力类型</th><th>压力价</th><th>距压力</th>
            <th>信号</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="r in srResults" :key="r.code" :class="{ 'row-highlight': r.signal }">
          <td>{{ r.code }}</td>
          <td>{{ r.name }}</td>
          <td>{{ r.price }}</td>
          <td>
            <span :class="r.pct_chg >= 0 ? 'text-red' : 'text-green'">{{ r.pct_chg }}%</span>
          </td>
          <td>{{ r.support_name }}</td>
          <td>{{ r.support_price || '--' }}</td>
          <td>
            <span :class="r.dist_support <= 3 ? 'text-green' : ''">
              {{ r.dist_support < 999 ? r.dist_support + '%' : '--' }}
            </span>
          </td>
          <td>{{ r.resistance_name }}</td>
          <td>{{ r.resistance_price || '--' }}</td>
          <td>
            <span :class="r.dist_resistance <= 3 ? 'text-red' : ''">
              {{ r.dist_resistance < 999 ? r.dist_resistance + '%' : '--' }}
            </span>
          </td>
          <td>
            <span v-if="r.signal" :class="['tag', r.signal_type.includes('buy') || r.signal_type === 'near_support' ? 'tag-high' : 'tag-low']">
              {{ r.signal }}
            </span>
            <span v-else style="color:#999;">--</span>
          </td>
        </tr>
        </tbody>
      </table>
    </div>
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

const sRLoading = ref(false)
const srResults = ref([])

const stockColumns = [
  { key: 'code', label: '代码' },
  { key: 'name', label: '名称' },
  { key: 'price', label: '最新价' },
  { key: 'pct_chg', label: '涨跌幅' },
  { key: 'volume', label: '成交量' },
]

const sortedStocks = computed(() =>
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
  loading.value = true; error.value = ''; stocks.value = []; srResults.value = []
  try {
    const r = await api.get('/sectors/' + encodeURIComponent(sector.value) + '/stocks')
    stocks.value = r.data || []
    if (!stocks.value.length) error.value = '无数据'
  } catch (e) { error.value = e.message }
  finally { loading.value = false }
}

async function scanSR() {
  if (!sector.value) return
  sRLoading.value = true; error.value = ''; srResults.value = []
  try {
    const r = await api.get('/sectors/' + encodeURIComponent(sector.value) + '/support-resistance')
    srResults.value = r.data || []
    if (!srResults.value.length) error.value = '扫描完成，未发现接近支撑/压力位的股票'
  } catch (e) { error.value = e.message }
  finally { sRLoading.value = false }
}
</script>
<style scoped>
.row-highlight { background: #fff8e1; }
</style>
