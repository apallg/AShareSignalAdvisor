<template>
  <div>
    <h1 class="page-title">
      策略实盘
      <span v-if="!cashEnabled" style="font-size:12px;color:#e94560;font-weight:normal;">QMT 实盘</span>
    </h1>
    <div v-if="error" class="error">{{ error }}</div>

    <!-- 策略启动卡片 -->
    <div class="card">
      <div class="card-title">启动策略运行器</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;">
        <div class="flex">
          <label style="width:60px;">策略</label>
          <select v-model="form.strategy_key" @change="onStrategyChange" style="flex:1;">
            <option value="">-- 选择策略 --</option>
            <option v-for="(info, key) in strategies" :key="key" :value="key" :disabled="!info.live_capable">
              {{ info.name }}{{ info.live_capable ? '' : ' (仅回测)' }}
            </option>
          </select>
        </div>
        <div class="flex">
          <label style="width:60px;">股票</label>
          <input v-model="form.symbol" placeholder="600519" style="flex:1;" />
        </div>
        <div class="flex">
          <label style="width:60px;">间隔</label>
          <select v-model.number="form.interval_sec" style="flex:1;">
            <option :value="10">10秒</option>
            <option :value="30">30秒</option>
            <option :value="60">1分钟</option>
            <option :value="300">5分钟</option>
            <option :value="900">15分钟</option>
          </select>
        </div>
      </div>
      <div v-if="selectedStrategy && selectedStrategy.live_params" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;margin-top:12px;">
        <div v-for="(defaultVal, pname) in selectedStrategy.live_params" :key="pname" class="flex">
          <label style="width:fit-content;min-width:80px;font-size:11px;white-space:nowrap;" :title="pname">{{ pname }}<span v-if="selectedStrategy.live_param_descs?.[pname]" style="color:#999;"> ({{ selectedStrategy.live_param_descs[pname] }})</span></label>
          <input v-model.number="form.params[pname]" type="number" style="flex:1;" />
        </div>
      </div>
      <div v-if="selectedStrategy && !selectedStrategy.live_capable" style="margin-top:12px;padding:8px 12px;background:#fff3cd;color:#856404;border-radius:4px;font-size:13px;">
        此策略暂无实盘版本，仅可在回测/实验室中使用
      </div>
      <button class="btn" style="margin-top:12px;" @click="startRunner" :disabled="loading || !selectedStrategy?.live_capable">
        {{ loading ? '启动中...' : '▶ 启动实盘运行' }}
      </button>
    </div>

    <!-- 运行中的策略 -->
    <div v-if="runners.length" class="card">
      <div class="card-title">运行中的策略 ({{ runners.length }})</div>
      <table>
        <tr><th>策略</th><th>股票</th><th>间隔</th><th>信号数</th><th>最后检查</th><th>状态</th><th>操作</th></tr>
        <tr v-for="r in runners" :key="r.id">
          <td>{{ r.strategy_name }}</td>
          <td>{{ r.symbol }}</td>
          <td>{{ r.interval_sec }}s</td>
          <td>{{ r.signals }}</td>
          <td>{{ r.last_check || '--' }}</td>
          <td><span class="tag tag-low">{{ r.status }}</span></td>
          <td>
            <button class="btn" style="background:#e74c3c;padding:4px 12px;font-size:12px" @click="stopRunner(r.id)">停止</button>
          </td>
        </tr>
      </table>
    </div>

    <!-- 账户总览 -->
    <div class="grid-4 mb-2" v-if="account.cash">
      <MetricCard value="¥{{ Number(account.cash || 0).toFixed(2) }}" label="现金" />
      <MetricCard value="¥{{ Number(account.market_value || 0).toFixed(2) }}" label="持仓市值" />
      <MetricCard value="¥{{ Number(account.total_assets || 0).toFixed(2) }}" label="总资产" />
      <MetricCard value="¥{{ Number(account.unrealized_pnl || 0).toFixed(2) }}" label="浮动盈亏" :color="(account.unrealized_pnl || 0) >= 0 ? 'up' : 'down'" />
    </div>

    <!-- 信号日志 -->
    <div v-if="signals.length" class="card">
      <div class="card-title">信号记录 ({{ signals.length }})</div>
      <table>
        <tr><th>时间</th><th>策略</th><th>股票</th><th>信号</th><th>原因</th><th>价格</th></tr>
        <tr v-for="(s, i) in signals.slice(0, 30)" :key="i">
          <td style="white-space:nowrap;">{{ s.time?.slice(5, 19) }}</td>
          <td>{{ s.strategy }}</td>
          <td>{{ s.symbol }}</td>
          <td>
            <span :class="['tag', s.action === 'buy' ? 'tag-high' : 'tag-low']">
              {{ s.action === 'buy' ? '买入' : '卖出' }}
            </span>
          </td>
          <td style="font-size:12px;">{{ s.reason }}</td>
          <td>{{ s.price }}</td>
        </tr>
      </table>
    </div>
    <div v-else class="card empty">暂无信号，启动策略后会在此显示</div>
  </div>
</template>
<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import api from '../api/index.js'
import MetricCard from '../components/MetricCard.vue'
import { useBroker } from '../composables/useBroker.js'

const { cashEnabled, loadBroker } = useBroker()

const strategies = ref({})
const runners = ref([])
const signals = ref([])
const account = ref({})
const loading = ref(false)
const error = ref('')

const form = ref({
  strategy_key: '',
  symbol: '600519',
  params: {},
  interval_sec: 60,
})

const selectedStrategy = computed(() =>
  form.value.strategy_key ? strategies.value[form.value.strategy_key] : null
)

let pollTimer = null
let accountTimer = null

function onStrategyChange() {
  const info = selectedStrategy.value
  form.value.params = {}
  if (info && info.live_params) {
    for (const [k, v] of Object.entries(info.live_params)) {
      form.value.params[k] = v
    }
  }
}

async function loadStrategies() {
  try {
    const r = await api.get('/live/strategies')
    strategies.value = r.data || {}
  } catch (e) { error.value = e.message }
}

async function loadStatus() {
  try {
    const [r, s] = await Promise.all([
      api.get('/live/status'),
      api.get('/live/signals?limit=30'),
    ])
    runners.value = r.data || []
    signals.value = s.data || []
  } catch (e) { /* 轮询中忽略错误 */ }
}

async function startRunner() {
  if (!form.value.strategy_key || !form.value.symbol.trim()) {
    error.value = '请选择策略和股票代码'; return
  }
  loading.value = true; error.value = ''
  try {
    await api.post('/live/start', { ...form.value })
    await loadStatus()
  } catch (e) { error.value = e.message }
  loading.value = false
}

async function stopRunner(id) {
  try {
    await api.post('/live/stop/' + id)
    await loadStatus()
  } catch (e) { error.value = e.message }
}

async function loadAccount() {
  try {
    const a = await api.get('/trading/account')
    account.value = a.data || {}
  } catch (e) { /* 忽略 */ }
}

onMounted(async () => {
  await loadBroker()
  await loadStrategies()
  await loadStatus()
  await loadAccount()
  pollTimer = setInterval(loadStatus, 5000)
  accountTimer = setInterval(loadAccount, 30000)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  if (accountTimer) clearInterval(accountTimer)
})
</script>
