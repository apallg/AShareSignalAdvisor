<template>
  <div>
    <h1 class="page-title">策略研发实验室</h1>
    <div v-if="error" class="error">{{ error }}</div>
    <div class="card">
      <div class="card-title">参数优化</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;">
        <div class="flex"><label style="width:80px;">策略</label>
          <select v-model="strategy" @change="onChange" style="flex:1;">
            <option value="">-- 选择 --</option>
            <option v-for="(v, k) in strategies" :key="k" :value="k">{{ v.name }}</option>
          </select></div>
        <div class="flex"><label style="width:80px;">方式</label>
          <select v-model="method" style="flex:1;"><option value="grid">网格搜索</option><option value="genetic">遗传算法</option></select></div>
        <div class="flex"><label style="width:80px;">股票</label><input v-model="codes" placeholder="600519,000001" style="flex:1;" /></div>
      </div>
      <div v-if="strategy && strategyParams.length" style="margin-top:12px;border-top:1px solid #eee;padding-top:12px;">
        <div class="card-title" style="font-size:13px;">优化参数范围</div>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:8px;">
          <div v-for="p in strategyParams" :key="p.name" class="flex">
            <label style="width:110px;font-size:12px;">{{ p.name }}<span v-if="p.desc" style="color:#999;font-size:10px;">({{ p.desc }})</span></label>
            <input v-model="paramRanges[p.name]" placeholder="1,5,10,20" style="flex:1;font-size:12px;" />
          </div>
        </div>
      </div>
      <button class="btn" style="margin-top:12px;" @click="runOptimize" :disabled="running">{{ running ? '优化中...' : '开始优化' }}</button>
    </div>
    <div v-if="result" class="card">
      <div class="card-title">优化结果</div>
      <table v-if="result.metrics">
        <tr><th>指标</th><th>最优值</th></tr>
        <tr>
          <td>年化收益</td>
          <td :class="(result.metrics.total_return || 0) > 0 ? 'text-red' : (result.metrics.total_return || 0) < 0 ? 'text-green' : ''">{{ result.metrics.total_return }}%</td>
        </tr>
        <tr><td>夏普比率</td><td>{{ result.metrics.sharpe }}</td></tr>
        <tr><td>最大回撤</td><td class="text-green">{{ result.metrics.max_drawdown }}%</td></tr>
        <tr><td>胜率</td><td>{{ result.metrics.win_rate }}%</td></tr>
        <tr><td>交易次数</td><td>{{ result.metrics.total_trades }}</td></tr>
      </table>
      <div class="card-title" style="margin-top:12px;font-size:13px;">最优参数</div>
      <pre style="background:#f5f5f5;padding:12px;border-radius:6px;font-size:13px;">{{ JSON.stringify(result.params, null, 2) }}</pre>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import api from '../api/index.js'

const strategies = ref({})
const strategy = ref('')
const method = ref('grid')
const codes = ref('600519')
const strategyParams = ref([])
const paramRanges = ref({})
const running = ref(false)
const error = ref('')
const result = ref(null)

async function load() {
  try { const r = await api.get('/backtest/strategies'); strategies.value = r.data || {} }
  catch (e) { error.value = e.message }
}
function onChange() {
  const info = strategies.value[strategy.value]
  if (info) {
    strategyParams.value = info.params || []
    paramRanges.value = {}
    info.params.forEach(p => { paramRanges.value[p.name] = String(p.default) })
  } else { strategyParams.value = []; paramRanges.value = {} }
}
async function runOptimize() {
  if (!strategy.value) { error.value = '请选择策略'; return }
  running.value = true; error.value = ''; result.value = null
  try {
    const grid = {}
    for (const k of Object.keys(paramRanges.value)) {
      const vals = paramRanges.value[k].split(',').map(Number).filter(v => !isNaN(v))
      if (vals.length) grid[k] = vals
    }
    const codeList = codes.value.split(',').map(c => c.trim()).filter(Boolean)
    if (!codeList.length) { error.value = '请输入股票代码'; return }
    const sd = new Date(Date.now() - 365 * 24 * 60 * 60 * 1000).toISOString().slice(0, 10).replace(/-/g, '')
    const ed = new Date().toISOString().slice(0, 10).replace(/-/g, '')
    const payload = { strategy_name: strategy.value, codes: codeList, start_date: sd, end_date: ed, param_grid: grid }
    const res = await api.post('/backtest/optimize', payload)
    const data = res.data || []
    result.value = data[0] || data
  } catch (e) { error.value = e.message }
  running.value = false
}
onMounted(load)
</script>
