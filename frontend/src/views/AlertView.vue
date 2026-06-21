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

    <div class="card mb-2" style="padding:12px 16px;">
      <div class="flex" style="align-items:center;gap:12px;">
        <span :class="['dot', sched.running ? 'dot-on' : 'dot-off']"></span>
        <span style="font-weight:600;">定时扫描</span>
        <span v-if="sched.running" class="tag tag-low">运行中</span>
        <span v-else class="tag tag-high">已停止</span>
        <span style="font-size:11px;color:#999;">
          早盘 {{ sched.morning_time }} | 尾盘 {{ sched.afternoon_time }} | 阈值 {{ sched.default_threshold }}
        </span>
        <div style="margin-left:auto;display:flex;gap:8px;">
          <button v-if="!sched.running" class="btn" style="padding:4px 12px;font-size:11px;background:#27ae60;" @click="schedStart">启动</button>
          <button v-if="sched.running" class="btn" style="padding:4px 12px;font-size:11px;background:#e94560;" @click="schedStop">停止</button>
          <button class="btn" style="padding:4px 12px;font-size:11px;" @click="schedTrigger" :disabled="schedTriggering">
            {{ schedTriggering ? '扫描中...' : '立即扫描' }}
          </button>
        </div>
      </div>
      <div v-if="sched.next_morning || sched.next_afternoon" style="margin-top:8px;font-size:11px;color:#999;">
        下次扫描:
        <span v-if="sched.next_morning">早盘 {{ fmtTime(sched.next_morning) }}</span>
        <span v-if="sched.next_morning && sched.next_afternoon"> | </span>
        <span v-if="sched.next_afternoon">尾盘 {{ fmtTime(sched.next_afternoon) }}</span>
      </div>
      <div v-if="sched.last_scan" style="margin-top:4px;font-size:11px;color:#999;">
        最近扫描: {{ fmtTime(sched.last_scan) }} — {{ sched.last_result }}
      </div>
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
        <tr><th>代码</th><th>名称</th><th>持股</th><th>成本</th><th>通知阈值</th><th>最近风险</th><th>操作</th></tr>
        <template v-for="h in holdings" :key="h.code">
          <tr>
            <td>{{ h.code }}</td>
            <td>{{ h.name }}</td>
            <td>{{ h.shares }}</td>
            <td>{{ Number(h.cost_price).toFixed(2) }}</td>
            <td>
              <select v-model.number="h.risk_threshold" @change="updateThreshold(h)" style="width:52px;font-size:11px;padding:2px;">
                <option v-for="n in 10" :key="n" :value="n">{{ n }}</option>
              </select>
            </td>
            <td>
              <span v-if="scannedCodes[h.code]"
                :class="['tag', riskTagClass(scannedCodes[h.code].risk_level)]"
                style="cursor:pointer;"
                @click="toggleDetail(h.code)">
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
          <tr v-if="expanded === h.code && scannedCodes[h.code]" class="detail-row">
            <td colspan="7">
              <div class="scan-detail">
                <div class="detail-header">
                  <span>{{ scannedCodes[h.code].stock_name }}({{ h.code }}) 风险详情</span>
                  <button class="btn" style="padding:2px 8px;font-size:11px;" @click="expanded = ''">收起</button>
                </div>
                <div class="detail-grid">
                  <div>
                    <div class="detail-label">风险评分</div>
                    <div class="detail-value">{{ scannedCodes[h.code].risk_score }}/10</div>
                  </div>
                  <div>
                    <div class="detail-label">风险等级</div>
                    <div class="detail-value">{{ scannedCodes[h.code].risk_level }}</div>
                  </div>
                  <div>
                    <div class="detail-label">当前价格</div>
                    <div class="detail-value">{{ scannedCodes[h.code].current_price || '--' }}</div>
                  </div>
                  <div>
                    <div class="detail-label">盈亏</div>
                    <div class="detail-value" :style="{color: scannedCodes[h.code].profit_loss >= 0 ? '#27ae60' : '#e94560'}">
                      {{ scannedCodes[h.code].profit_loss?.toFixed(2) || '--' }}
                      ({{ scannedCodes[h.code].profit_loss_pct?.toFixed(2) || '--' }}%)
                    </div>
                  </div>
                </div>
                <div v-if="scannedCodes[h.code].suggestion" class="detail-section">
                  <div class="detail-label">操作建议</div>
                  <div class="detail-text">{{ scannedCodes[h.code].suggestion }}</div>
                </div>
                <div class="detail-section">
                  <div class="detail-label">分析详情</div>
                  <div class="detail-text" style="white-space:pre-wrap;max-height:400px;overflow-y:auto;">{{ scannedCodes[h.code].risk_detail }}</div>
                </div>
                <div v-if="scannedCodes[h.code].data_enabled" style="font-size:11px;color:#999;margin-top:8px;">
                  数据源: {{ scannedCodes[h.code].data_enabled.join('、') }}
                  <span v-if="scannedCodes[h.code].data_skipped?.length"> | 跳过: {{ scannedCodes[h.code].data_skipped.join('、') }}</span>
                </div>
              </div>
            </td>
          </tr>
        </template>
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
import { ref, reactive, computed, onMounted, onUnmounted } from 'vue'
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
const expanded = ref('')
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

function riskTagClass(level) {
  return level === '高风险' ? 'tag-high' : level === '中风险' ? 'tag-mid' : 'tag-low'
}

function toggleDetail(code) {
  expanded.value = expanded.value === code ? '' : code
}

async function updateThreshold(h) {
  try {
    await api.put(`/portfolio/holdings/${h.code}`, { risk_threshold: h.risk_threshold })
  } catch (e) { /* 忽略 */ }
}

async function loadHoldings() {
  try {
    const r = await api.get('/portfolio/holdings')
    holdings.value = (r.data || []).map(h => ({
      ...h,
      risk_threshold: h.risk_threshold || 7,
    }))
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
      expanded.value = code
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

const sched = reactive({
  running: false,
  morning_time: '',
  afternoon_time: '',
  default_threshold: 7,
  last_scan: null,
  last_result: null,
  next_morning: null,
  next_afternoon: null,
})
const schedTriggering = ref(false)
let schedTimer = null

function fmtTime(s) {
  if (!s) return '--'
  return s.slice(0, 16).replace('T', ' ')
}

async function loadSchedStatus() {
  try {
    const r = await api.get('/scheduler/status')
    if (r.data) Object.assign(sched, r.data)
  } catch (e) { /* 忽略 */ }
}

async function schedStart() {
  try { await api.post('/scheduler/start'); await loadSchedStatus() } catch (e) { /* 忽略 */ }
}
async function schedStop() {
  try { await api.post('/scheduler/stop'); await loadSchedStatus() } catch (e) { /* 忽略 */ }
}
async function schedTrigger() {
  schedTriggering.value = true
  try {
    await api.post('/scheduler/trigger')
    await loadSchedStatus()
    await loadData()
    msg.value = '手动扫描已触发，请等待完成...'
    setTimeout(async () => { await loadSchedStatus(); await loadData(); msg.value = '' }, 30000)
  } catch (e) { error.value = e.message }
  schedTriggering.value = false
}

onMounted(() => {
  loadHoldings(); loadChannels(); loadData(); loadSchedStatus()
  schedTimer = setInterval(loadSchedStatus, 30000)
})
onUnmounted(() => {
  clearInterval(schedTimer)
})
</script>
<style scoped>
.dot {
  width: 8px; height: 8px; border-radius: 50%; display: inline-block;
}
.dot-on { background: #27ae60; }
.dot-off { background: #e94560; }
.detail-row td {
  padding: 0;
  background: #0f1825;
}
.scan-detail {
  padding: 16px 20px;
  border-top: 1px solid #1e2d3d;
}
.detail-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  font-weight: 600;
  font-size: 14px;
}
.detail-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
  margin-bottom: 12px;
}
.detail-label {
  font-size: 11px;
  color: #999;
  margin-bottom: 2px;
}
.detail-value {
  font-size: 14px;
  font-weight: 600;
}
.detail-section {
  margin-top: 10px;
}
.detail-text {
  font-size: 12px;
  color: #ccc;
  margin-top: 4px;
  line-height: 1.6;
  background: #060d15;
  padding: 10px 14px;
  border-radius: 6px;
}
</style>
