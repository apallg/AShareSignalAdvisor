<template>
  <div>
    <h1 class="page-title">风险告警</h1>
    <div v-if="error" class="error">{{ error }}</div>
    <div v-if="msg" class="msg">{{ msg }}</div>

    <div class="grid-4 mb-2">
      <MetricCard :value="stats.high" label="高风险" color="up" />
      <MetricCard :value="stats.mid" label="中风险" />
      <MetricCard :value="stats.low" label="低风险" color="down" />
    </div>

    <div class="flex mb-2" style="gap:12px;align-items:center;">
      <span v-if="channels.wecom" class="tag tag-low">企业微信</span>
      <span v-if="channels.coze" class="tag tag-mid">Coze</span>
      <span v-if="!channels.wecom && !channels.coze" style="font-size:12px;color:#e94560;">通知通道未配置</span>
      <button class="btn" style="margin-left:auto;padding:6px 16px;font-size:12px;" @click="testNotify" :disabled="testing">
        {{ testing ? '发送中...' : '测试通知' }}
      </button>
    </div>

    <div class="card" v-if="holdings.length">
      <div class="card-title">
        持仓扫描
        <span style="font-weight:normal;font-size:12px;color:#999;margin-left:8px;">{{ holdings.length }} 只</span>
      </div>
      <div class="flex mb-2" style="gap:12px;align-items:center;flex-wrap:wrap;">
        <label style="font-size:11px;"><input type="checkbox" v-model="include.technical" /> 技术指标</label>
        <label style="font-size:11px;"><input type="checkbox" v-model="include.financial" /> 财务指标</label>
        <label style="font-size:11px;"><input type="checkbox" v-model="include.patterns" /> K线形态</label>
        <label style="font-size:11px;"><input type="checkbox" v-model="include.realtime" /> 实时行情</label>
        <span style="font-size:11px;color:#999;">日K线(必选)</span>
        <select v-model.number="scanThreshold" style="width:80px;margin-left:auto;">
          <option :value="0">全部</option>
          <option :value="5">≥5</option>
          <option :value="7">≥7</option>
        </select>
        <button class="btn" style="padding:6px 16px;font-size:12px;background:#27ae60;" @click="batchScan" :disabled="scanning">
          {{ scanning ? '批量扫描中...' : '批量扫描' }}
        </button>
      </div>
      <table>
        <tr><th>代码</th><th>名称</th><th>持股</th><th>成本</th><th>告警</th><th>最近风险</th><th>操作</th></tr>
        <tr v-for="h in holdings" :key="h.code">
          <td>{{ h.code }}</td>
          <td>{{ h.name }}</td>
          <td>{{ h.shares }}</td>
          <td>{{ Number(h.cost_price).toFixed(2) }}</td>
          <td>{{ h.alerts_enabled ? '开启' : '关闭' }}</td>
          <td>
            <span v-if="scannedCodes[h.code]" :class="['tag', scannedCodes[h.code].risk_level === '高风险' ? 'tag-high' : scannedCodes[h.code].risk_level === '中风险' ? 'tag-mid' : 'tag-low']">
              {{ scannedCodes[h.code].risk_level }} {{ scannedCodes[h.code].risk_score }}/10
            </span>
            <span v-else style="color:#999;">--</span>
          </td>
          <td>
            <button class="btn" style="padding:4px 12px;font-size:11px;" @click="scanOne(h.code)" :disabled="singleScanning === h.code">
              {{ singleScanning === h.code ? '扫描中...' : '扫描' }}
            </button>
          </td>
        </tr>
      </table>
    </div>
    <div v-else class="card empty">暂无持仓，请先在持仓管理中添加股票</div>

    <div class="flex mb-2" style="gap:12px;align-items:center;margin-top:16px;">
      <select v-model="levelFilter">
        <option value="">全部等级</option>
        <option value="高风险">高风险</option>
        <option value="中风险">中风险</option>
        <option value="低风险">低风险</option>
      </select>
    </div>

    <DataTable
      :rows="filtered"
      :columns="columns"
      row-key="id"
      empty-text="暂无告警记录"
    >
      <template #cell-stock_name="{ row }">{{ row.stock_name }}({{ row.stock_code }})</template>
      <template #cell-risk_level="{ value }">
        <span :class="['tag', value==='高风险'?'tag-high':value==='中风险'?'tag-mid':'tag-low']">{{ value }}</span>
      </template>
      <template #cell-risk_score="{ value }">{{ value }}/10</template>
      <template #cell-risk_detail="{ value }">
        <span style="font-size:12px;display:block;max-width:300px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" :title="value">{{ value?.slice(0, 80) }}</span>
      </template>
      <template #cell-created_at="{ value }">
        <span style="white-space:nowrap">{{ value?.slice(0,16) || '--' }}</span>
      </template>
    </DataTable>
  </div>
</template>
<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import api from '../api/index.js'
import MetricCard from '../components/MetricCard.vue'
import DataTable from '../components/DataTable.vue'

const alerts = ref([])
const stats = ref({ high: 0, mid: 0, low: 0 })
const channels = ref({ wecom: false, coze: false })
const holdings = ref([])
const scannedCodes = ref({})
const levelFilter = ref('')
const scanThreshold = ref(5)
const error = ref('')
const msg = ref('')
const testing = ref(false)
const scanning = ref(false)
const singleScanning = ref('')
const include = reactive({
  technical: true,
  financial: true,
  patterns: true,
  realtime: true,
})

const columns = [
  { key: 'stock_name', label: '股票' },
  { key: 'risk_level', label: '等级' },
  { key: 'risk_score', label: '评分' },
  { key: 'risk_detail', label: '详情' },
  { key: 'created_at', label: '时间' },
]

const filtered = computed(() =>
  !levelFilter.value ? alerts.value : alerts.value.filter(a => a.risk_level === levelFilter.value)
)

async function loadHoldings() {
  try {
    const r = await api.get('/portfolio/holdings')
    holdings.value = r.data || []
  } catch (e) { /* 忽略 */ }
}

async function loadChannels() {
  try {
    const r = await api.get('/alerts/channels')
    channels.value = r.data || {}
  } catch (e) { /* 忽略 */ }
}

async function testNotify() {
  testing.value = true; msg.value = ''; error.value = ''
  try {
    const r = await api.post('/alerts/test')
    msg.value = '测试通知已发送: ' + JSON.stringify(r.data)
  } catch (e) { error.value = e.message }
  testing.value = false
}

function getScanParams() {
  const params = {}
  for (const [k, v] of Object.entries(include)) {
    if (!v) params[k] = false
  }
  return Object.keys(params).length ? params : null
}

async function scanOne(code) {
  singleScanning.value = code; msg.value = ''; error.value = ''
  try {
    const payload = { threshold: 0 }
    const inc = getScanParams()
    if (inc) payload.include = inc
    const r = await api.post(`/alerts/scan/${code}`, payload)
    if (r.data) {
      scannedCodes.value[code] = r.data
    }
    await loadData()
  } catch (e) { error.value = e.message }
  singleScanning.value = ''
}

async function batchScan() {
  scanning.value = true; msg.value = ''; error.value = ''
  try {
    const payload = { threshold: scanThreshold.value }
    const inc = getScanParams()
    if (inc) payload.include = inc
    const r = await api.post('/alerts/scan', payload)
    const results = r.data?.results || []
    for (const item of results) {
      scannedCodes.value[item.stock_code] = item
    }
    msg.value = `扫描完成，发现 ${r.data?.count || 0} 条风险记录`
    await loadData()
  } catch (e) { error.value = e.message }
  scanning.value = false
}

async function loadData() {
  try {
    const [a, s] = await Promise.all([
      api.get('/alerts/?limit=100'),
      api.get('/alerts/stats?limit=200'),
    ])
    alerts.value = a.data || []
    stats.value = s.data || { high: 0, mid: 0, low: 0 }
  } catch (e) { error.value = e.message }
}

onMounted(() => { loadHoldings(); loadChannels(); loadData() })
</script>
