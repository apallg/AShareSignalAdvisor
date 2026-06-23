<template>
  <div>
    <h1 class="page-title">板块选股</h1>

    <!-- 热门板块 Top 20 -->
    <div class="card" style="margin-bottom:16px;">
      <div class="card-title">热门板块 Top 20 <span style="font-weight:normal;font-size:12px;color:#999;">点击快速选择</span></div>
      <div class="hot-tags">
        <span v-for="h in hotSectors" :key="h.name"
              class="hot-tag"
              :class="{ 'hot-up': h.pct_chg > 0, 'hot-down': h.pct_chg < 0, 'hot-selected': sector === h.name }"
              @click="selectHot(h.name)">
          {{ h.name }}
          <span class="hot-pct">{{ h.pct_chg > 0 ? '+' : '' }}{{ h.pct_chg }}%</span>
        </span>
      </div>
    </div>

    <!-- 操作栏 -->
    <div class="flex mb-2" style="gap:8px;">
      <select v-model="sector" style="flex:1;padding:8px 14px;border:1px solid #ddd;border-radius:6px;font-size:14px;">
        <option value="">-- 选择板块 --</option>
        <option v-for="s in sectors" :key="s" :value="s">{{ s }}</option>
      </select>
      <button class="btn" @click="search">查询成分股</button>
      <button class="btn" style="background:#e94560;" @click="scanSR" :disabled="sRLoading">
        {{ sRLoading ? '扫描中...' : 'SR扫描' }}
      </button>
      <button class="btn" style="background:#8b5cf6;" @click="scanDZ" :disabled="dzLoading">
        {{ dzLoading ? '密集区分析中...' : '密集区' }}
      </button>
    </div>

    <!-- 全板块扫描按钮 -->
    <div class="flex mb-2" style="gap:8px;">
      <button class="btn" style="background:#e94560;flex:1;" @click="scanAllSR" :disabled="allSrLoading">
        {{ allSrLoading ? '全板块SR扫描中...' : '全板块支撑/压力扫描' }}
      </button>
      <button class="btn" style="background:#8b5cf6;flex:1;" @click="scanAllDZ" :disabled="allDzLoading">
        {{ allDzLoading ? '全板块密集区分析中...' : '全板块密集区分析' }}
      </button>
    </div>

    <div v-if="error" class="error" style="display:flex;align-items:center;justify-content:space-between;">
      <span>{{ error }}</span>
      <button v-if="lastAction" class="btn" style="background:#e94560;padding:4px 14px;font-size:12px;" @click="retry">重试</button>
    </div>
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

    <!-- 支撑/压力位扫描结果（单板块） -->
    <div v-if="srResults.length" class="card" style="margin-top:16px;">
      <div class="card-title">
        支撑/压力位扫描结果 ({{ srResults.length }} 只)
        <span style="font-weight:normal;font-size:12px;color:#999;margin-left:8px;">
          离支撑/压力位 &lt;3% 视为接近
        </span>
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr>
          <th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th>
          <th>支撑类型</th><th>支撑价</th><th>距支撑</th>
          <th>压力类型</th><th>压力价</th><th>距压力</th>
          <th>信号</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in srResults" :key="r.code" :class="{ 'row-highlight': r.signal }">
          <td>{{ r.code }}</td>
          <td>{{ r.name }}</td>
          <td>{{ r.price }}</td>
          <td><span :class="r.pct_chg >= 0 ? 'text-red' : 'text-green'">{{ r.pct_chg }}%</span></td>
          <td>{{ r.support_name }}</td>
          <td>{{ r.support_price || '--' }}</td>
          <td><span :class="r.dist_support <= 3 ? 'text-green' : ''">{{ r.dist_support < 999 ? r.dist_support + '%' : '--' }}</span></td>
          <td>{{ r.resistance_name }}</td>
          <td>{{ r.resistance_price || '--' }}</td>
          <td><span :class="r.dist_resistance <= 3 ? 'text-red' : ''">{{ r.dist_resistance < 999 ? r.dist_resistance + '%' : '--' }}</span></td>
          <td>
            <span v-if="r.signal" :class="['tag', r.signal_type.includes('buy') || r.signal_type === 'near_support' ? 'tag-high' : 'tag-low']">{{ r.signal }}</span>
            <span v-else style="color:#999;">--</span>
          </td>
        </tr></tbody>
      </table></div>
    </div>

    <!-- 密集区分析结果（单板块） -->
    <div v-if="dzResult && dzResult.scanned" class="card" style="margin-top:16px;">
      <div class="card-title">
        成交密集区分析 - {{ dzResult.sector }}
        <span :class="['tag', dzStatusClass]">{{ dzResult.status }}</span>
      </div>
      <div class="kpi-row">
        <MetricCard :value="dzResult.scanned + '/' + dzResult.total" label="扫描数" />
        <MetricCard :value="dzResult.support_pct + '%'" label="支撑占比" custom-color="#00ff88" />
        <MetricCard :value="dzResult.resistance_pct + '%'" label="压力占比" custom-color="#ff4466" />
        <MetricCard :value="dzResult.avg_rr" label="平均盈亏比" custom-color="#00d4ff" />
        <MetricCard :value="dzResult.neutral_pct + '%'" label="中性占比" />
      </div>
      <div class="tbl-wrap"><table style="margin-top:12px;">
        <thead><tr>
          <th>代码</th><th>名称</th><th>现价</th>
          <th>支撑区</th><th>距支撑</th>
          <th>压力区</th><th>距压力</th>
          <th>盈亏比</th><th>评级</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in dzResult.stocks" :key="r.code" :class="{ 'row-dz-signal': r.rr_ratio >= 2.5 }">
          <td>{{ r.code }}</td><td>{{ r.name }}</td><td>{{ r.price }}</td>
          <td><span v-if="r.nearest_support" class="text-green">¥{{ r.nearest_support }}</span><span v-else style="color:#999;">--</span></td>
          <td><span v-if="r.support_dist_pct" :class="r.support_dist_pct <= 2 ? 'text-green' : ''">{{ r.support_dist_pct }}%</span></td>
          <td><span v-if="r.nearest_resistance" class="text-red">¥{{ r.nearest_resistance }}</span><span v-else style="color:#999;">--</span></td>
          <td><span v-if="r.resistance_dist_pct" :class="r.resistance_dist_pct <= 2 ? 'text-red' : ''">{{ r.resistance_dist_pct }}%</span></td>
          <td><strong :style="{ color: r.rr_ratio >= 2.5 ? 'var(--g)' : r.rr_ratio >= 1.5 ? 'var(--c)' : 'inherit' }">{{ r.rr_ratio }}</strong></td>
          <td><span :class="['tag', rrTagClass(r.rr_quality)]">{{ r.rr_quality }}</span></td>
        </tr></tbody>
      </table></div>
      <div v-if="!dzResult.stocks.length" style="text-align:center;color:#999;padding:24px;">未发现符合条件的股票</div>
    </div>

    <!-- 全板块SR扫描结果 -->
    <div v-if="allSrResults.length" class="card" style="margin-top:16px;">
      <div class="card-title">
        全板块支撑/压力扫描 ({{ allSrResults.length }} 只)
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr>
          <th>板块</th><th>代码</th><th>最新价</th><th>涨跌幅</th>
          <th>支撑类型</th><th>支撑价</th><th>距支撑</th>
          <th>压力类型</th><th>压力价</th><th>距压力</th>
          <th>信号</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in allSrResults" :key="r.code" :class="{ 'row-highlight': r.signal }">
          <td class="sector-col">{{ (r.sectors || []).slice(0, 2).join('/') }}</td>
          <td>{{ r.code }}</td>
          <td>{{ r.price }}</td>
          <td><span :class="r.pct_chg >= 0 ? 'text-red' : 'text-green'">{{ r.pct_chg }}%</span></td>
          <td>{{ r.support_name }}</td>
          <td>{{ r.support_price || '--' }}</td>
          <td><span :class="r.dist_support <= 3 ? 'text-green' : ''">{{ r.dist_support < 999 ? r.dist_support + '%' : '--' }}</span></td>
          <td>{{ r.resistance_name }}</td>
          <td>{{ r.resistance_price || '--' }}</td>
          <td><span :class="r.dist_resistance <= 3 ? 'text-red' : ''">{{ r.dist_resistance < 999 ? r.dist_resistance + '%' : '--' }}</span></td>
          <td>
            <span v-if="r.signal" :class="['tag', r.signal_type.includes('buy') || r.signal_type === 'near_support' ? 'tag-high' : 'tag-low']">{{ r.signal }}</span>
            <span v-else style="color:#999;">--</span>
          </td>
        </tr></tbody>
      </table></div>
    </div>

    <!-- 全板块密集区扫描结果 -->
    <div v-if="allDzResults.length" class="card" style="margin-top:16px;">
      <div class="card-title">
        全板块密集区分析 ({{ allDzResults.length }} 只，按盈亏比排序)
      </div>
      <div class="tbl-wrap"><table>
        <thead><tr>
          <th>板块</th><th>代码</th><th>名称</th><th>现价</th>
          <th>支撑区</th><th>距支撑</th>
          <th>压力区</th><th>距压力</th>
          <th>盈亏比</th><th>评级</th>
        </tr></thead>
        <tbody>
          <tr v-for="r in allDzResults" :key="r.code" :class="{ 'row-dz-signal': r.rr_ratio >= 2.5 }">
          <td class="sector-col">{{ (r.sectors || []).slice(0, 2).join('/') }}</td>
          <td>{{ r.code }}</td><td>{{ r.name }}</td><td>{{ r.price }}</td>
          <td><span v-if="r.nearest_support" class="text-green">¥{{ r.nearest_support }}</span><span v-else style="color:#999;">--</span></td>
          <td><span v-if="r.support_dist_pct" :class="r.support_dist_pct <= 2 ? 'text-green' : ''">{{ r.support_dist_pct }}%</span></td>
          <td><span v-if="r.nearest_resistance" class="text-red">¥{{ r.nearest_resistance }}</span><span v-else style="color:#999;">--</span></td>
          <td><span v-if="r.resistance_dist_pct" :class="r.resistance_dist_pct <= 2 ? 'text-red' : ''">{{ r.resistance_dist_pct }}%</span></td>
          <td><strong :style="{ color: r.rr_ratio >= 2.5 ? 'var(--g)' : r.rr_ratio >= 1.5 ? 'var(--c)' : 'inherit' }">{{ r.rr_ratio }}</strong></td>
          <td><span :class="['tag', rrTagClass(r.rr_quality)]">{{ r.rr_quality }}</span></td>
        </tr></tbody>
      </table></div>
    </div>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from 'vue'
import api from '../api/index.js'
import DataTable from '../components/DataTable.vue'
import LoadingSpinner from '../components/LoadingSpinner.vue'
import MetricCard from '../components/MetricCard.vue'

const sectors = ref([])
const sector = ref('')
const stocks = ref([])
const loading = ref(false)
const error = ref('')

const sRLoading = ref(false)
const srResults = ref([])

const dzLoading = ref(false)
const dzResult = ref(null)

const hotSectors = ref([])

const allSrLoading = ref(false)
const allSrResults = ref([])

const allDzLoading = ref(false)
const allDzResults = ref([])

const lastAction = ref('')

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

const dzStatusClass = computed(() => {
  if (!dzResult.value) return ''
  if (dzResult.value.status === '偏多') return 'tag-high'
  if (dzResult.value.status === '偏空') return 'tag-low'
  return 'tag-neutral'
})

function rrTagClass(quality) {
  if (quality === '优秀' || quality === '良好') return 'tag-high'
  if (quality === '一般') return 'tag-neutral'
  return 'tag-low'
}

function selectHot(name) {
  sector.value = name
  search()
}

function retry() {
  if (!lastAction.value) return
  error.value = ''
  const actions = { search, scanSR, scanDZ, scanAllSR, scanAllDZ, onMounted }
  actions[lastAction.value]?.()
}

onMounted(async () => {
  lastAction.value = 'onMounted'
  try {
    const [secRes, hotRes] = await Promise.all([
      api.get('/sectors/list'),
      api.get('/sectors/hot?limit=20'),
    ])
    if (secRes.error) {
      error.value = `板块列表: ${secRes.error}`
    } else {
      sectors.value = (secRes.data || []).map(s => s['板块名称'] || s.board_name || s.name)
    }
    if (hotRes.error) {
      if (!error.value) error.value = `热门板块: ${hotRes.error}`
    } else {
      hotSectors.value = hotRes.data || []
    }
  } catch (e) { error.value = e.message }
})

async function search() {
  if (!sector.value) return
  lastAction.value = 'search'
  loading.value = true; error.value = ''; stocks.value = []; srResults.value = []
  try {
    const r = await api.get('/sectors/' + encodeURIComponent(sector.value) + '/stocks')
    if (r.error) { error.value = r.error; return }
    stocks.value = r.data || []
    if (!stocks.value.length) error.value = '无数据'
  } catch (e) { error.value = e.message }
  finally { loading.value = false }
}

async function scanSR() {
  if (!sector.value) return
  lastAction.value = 'scanSR'
  sRLoading.value = true; error.value = ''; srResults.value = []
  try {
    const r = await api.get('/sectors/' + encodeURIComponent(sector.value) + '/support-resistance')
    if (r.error) { error.value = r.error; return }
    srResults.value = r.data || []
    if (!srResults.value.length) error.value = '扫描完成，未发现接近支撑/压力位的股票'
  } catch (e) { error.value = e.message }
  finally { sRLoading.value = false }
}

async function scanDZ() {
  if (!sector.value) return
  lastAction.value = 'scanDZ'
  dzLoading.value = true; error.value = ''; dzResult.value = null
  try {
    const r = await api.get('/sectors/' + encodeURIComponent(sector.value) + '/dense-zones')
    if (r.error) { error.value = r.error; return }
    dzResult.value = r.data || {}
    if (!dzResult.value.scanned) error.value = '密集区分析完成，未获取到有效数据'
  } catch (e) { error.value = e.message }
  finally { dzLoading.value = false }
}

async function scanAllSR() {
  lastAction.value = 'scanAllSR'
  allSrLoading.value = true; error.value = ''; allSrResults.value = []
  try {
    const r = await api.get('/sectors/scan-all')
    if (r.error) { error.value = r.error; return }
    allSrResults.value = r.data || []
    if (!allSrResults.value.length) error.value = '全板块扫描完成，未发现支撑/压力信号'
  } catch (e) { error.value = e.message }
  finally { allSrLoading.value = false }
}

async function scanAllDZ() {
  lastAction.value = 'scanAllDZ'
  allDzLoading.value = true; error.value = ''; allDzResults.value = []
  try {
    const r = await api.get('/sectors/dense-zones-all')
    if (r.error) { error.value = r.error; return }
    allDzResults.value = r.data || []
    if (!allDzResults.value.length) error.value = '全板块密集区分析完成，未获取到有效数据'
  } catch (e) { error.value = e.message }
  finally { allDzLoading.value = false }
}
</script>
<style scoped>
.row-highlight { background: #fff8e1; }
.row-dz-signal { background: rgba(0, 255, 136, 0.04); }
.kpi-row { display: flex; gap: 12px; flex-wrap: wrap; margin-top: 8px; }
.tag-neutral {
  background: rgba(0, 212, 255, 0.12); color: var(--c);
  padding: 2px 8px; border-radius: 4px; font-size: 12px;
}
.tbl-wrap { max-height: 500px; overflow-y: auto; }
.sector-col { font-size: 11px; color: #888; max-width: 100px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.hot-tags {
  display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px;
}
.hot-tag {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 5px 12px; border-radius: 16px; font-size: 13px;
  cursor: pointer; transition: all .2s;
  border: 1px solid #e0e0e0; background: #fafafa;
}
.hot-tag:hover { transform: translateY(-1px); box-shadow: 0 2px 8px rgba(0,0,0,0.1); }
.hot-tag.hot-up { border-color: rgba(239, 83, 80, 0.3); background: rgba(239, 83, 80, 0.04); }
.hot-tag.hot-down { border-color: rgba(38, 166, 154, 0.3); background: rgba(38, 166, 154, 0.04); }
.hot-tag.hot-selected { border-color: #8b5cf6; background: rgba(139, 92, 246, 0.08); }
.hot-pct { font-weight: 600; font-size: 12px; }
.hot-up .hot-pct { color: #ef5350; }
.hot-down .hot-pct { color: #26a69a; }
</style>
