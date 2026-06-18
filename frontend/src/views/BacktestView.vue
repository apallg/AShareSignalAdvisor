<template>
  <div>
    <h1 class="page-title">策略回测</h1>
    <div v-if="error" class="error">{{ error }}</div>

    <!-- 回测配置 -->
    <div class="card">
      <div class="card-title">回测配置</div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
        <div class="flex">
          <label style="width:80px;flex-shrink:0;">策略</label>
          <select v-model="selectedStrategy" @change="onStrategyChange" style="flex:1;">
            <option value="">-- 选择策略 --</option>
            <option v-for="(info, name) in strategies" :key="name" :value="name">{{ info.name }}</option>
          </select>
        </div>
        <div class="flex">
          <label style="width:80px;flex-shrink:0;">股票</label>
          <input v-model="codes" placeholder="600519,000001" style="flex:1;" />
        </div>
      </div>

      <!-- 动态参数表单 -->
      <div v-if="selectedStrategy && strategyParams.length" style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:12px;">
        <div v-for="p in strategyParams" :key="p.name" class="flex">
          <label style="width:100px;flex-shrink:0;font-size:13px;">{{ p.name }}</label>
          <input v-if="p.type==='int'||p.type==='float'" v-model.number="paramValues[p.name]" :type="p.type==='float'?'number':'number'" :step="p.type==='float'?0.1:1" :min="p.min||0" :max="p.max||100" style="flex:1;" />
          <input v-else v-model="paramValues[p.name]" style="flex:1;" />
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr 1fr 1fr;gap:12px;margin-top:12px;">
        <div class="flex"><label style="width:60px;">开始</label><input v-model="startDate" type="date" style="flex:1;" /></div>
        <div class="flex"><label style="width:60px;">结束</label><input v-model="endDate" type="date" style="flex:1;" /></div>
        <div class="flex"><label style="width:60px;">资金</label><input v-model.number="cash" type="number" step="100000" style="flex:1;" /></div>
        <div class="flex"><label style="width:60px;">佣金</label><input v-model.number="commission" type="number" step="0.0001" style="flex:1;" /></div>
      </div>

      <button class="btn" style="margin-top:12px;" @click="runBacktest" :disabled="running">
        {{ running ? "回测中..." : "▶ 运行回测" }}
      </button>
    </div>

    <!-- 绩效指标 -->
    <div v-if="result" class="grid-4 mb-2">
      <div class="card metric"><div class="value" :class="(result.metrics.total_return||0)>0?'text-red':(result.metrics.total_return||0)<0?'text-green':''">{{ result.metrics.total_return ?? "--" }}%</div><div class="label"><TermTooltip name="年化收益">年化收益</TermTooltip></div></div>
      <div class="card metric"><div class="value">{{ result.metrics.sharpe ?? "--" }}</div><div class="label"><TermTooltip name="夏普比率">夏普比率</TermTooltip></div></div>
      <div class="card metric"><div class="value text-green">{{ result.metrics.max_drawdown ?? "--" }}%</div><div class="label"><TermTooltip name="最大回撤">最大回撤</TermTooltip></div></div>
      <div class="card metric"><div class="value">{{ result.metrics.win_rate ?? "--" }}%</div><div class="label"><TermTooltip name="胜率">胜率</TermTooltip></div></div>
    </div>

    <!-- 额外指标 -->
    <div v-if="result" class="grid-4 mb-2">
      <div class="card metric"><div class="value">{{ result.metrics.total_trades ?? "--" }}</div><div class="label"><TermTooltip name="总交易次数">总交易次数</TermTooltip></div></div>
      <div class="card metric"><div class="value">{{ result.metrics.profit_loss_ratio ?? "--" }}</div><div class="label"><TermTooltip name="盈亏比">盈亏比</TermTooltip></div></div>
    </div>

    <!-- 资金曲线 -->
    <div v-if="chartData" class="card">
      <div class="card-title">资金曲线</div>
      <div ref="chartRef" class="chart-box"></div>
    </div>

    <!-- 交易记录 -->
    <div v-if="trades.length" class="card">
      <div class="card-title">交易记录 ({{ trades.length }} 笔)</div>
      <table>
        <tr><th>日期</th><th>操作</th><th>价格</th><th>数量</th><th>盈亏</th><th>原因</th></tr>
        <tr v-for="(t, i) in trades" :key="i">
          <td>{{ t.date }}</td>
          <td :class="t.action==='buy'?'text-red':'text-green'">{{ t.action==='buy'?'买入':'卖出' }}</td>
          <td>{{ t.price }}</td>
          <td>{{ t.shares }}</td>
          <td :class="(t.pnl||0)>0?'text-red':(t.pnl||0)<0?'text-green':''">{{ t.pnl != null ? t.pnl.toFixed(2) : "--" }}</td>
          <td>{{ t.reason }}</td>
        </tr>
      </table>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted, nextTick } from "vue"
import api from "../api/index.js"
import * as echarts from "echarts"
import TermTooltip from "../components/TermTooltip.vue"

const error = ref("")
const loading = ref(false)
const strategies = ref({})
const selectedStrategy = ref("")
const strategyParams = ref([])
const paramValues = ref({})
const codes = ref("600519")
const startDate = ref("2023-01-01")
const endDate = ref("2024-12-31")
const cash = ref(1000000)
const commission = ref(0.0003)
const running = ref(false)
const result = ref(null)
const trades = ref([])
const chartRef = ref(null)
const chartData = ref(null)
let chartInstance = null

const formatDate = (d) => d.replace(/-/g, "")

async function loadStrategies() {
  try {
    const res = await api.get("/backtest/strategies")
    strategies.value = res.data || {}
  } catch (e) {
    error.value = e.message
  }
}

function onStrategyChange() {
  const info = strategies.value[selectedStrategy.value]
  if (info) {
    strategyParams.value = info.params || []
    paramValues.value = {}
    info.params.forEach((p) => {
      paramValues.value[p.name] = p.default
    })
  } else {
    strategyParams.value = []
    paramValues.value = {}
  }
}

async function runBacktest() {
  if (!selectedStrategy.value) {
    error.value = "请选择策略"
    return
  }
  running.value = true
  error.value = ""
  result.value = null
  trades.value = []
  chartData.value = null

  try {
    const codeList = codes.value.split(",").map((c) => c.trim()).filter(Boolean)
    const payload = {
      strategy_name: selectedStrategy.value,
      params: { ...paramValues.value },
      codes: codeList,
      start_date: formatDate(startDate.value),
      end_date: formatDate(endDate.value),
      cash: cash.value,
      commission: commission.value,
    }
    const res = await api.post("/backtest/run", payload)
    const data = res.data || []
    if (data.length > 0) {
      result.value = data[0]
      trades.value = data[0].trades || []
      chartData.value = data[0].equity_curve || []
      await nextTick()
      renderChart()
    } else {
      error.value = "回测无数据返回"
    }
  } catch (e) {
    error.value = "回测失败: " + e.message
  }
  running.value = false
}

function renderChart() {
  const el = chartRef.value
  if (!el || !chartData.value || !chartData.value.length) return
  if (chartInstance) { chartInstance.dispose(); chartInstance = null }
  chartInstance = echarts.init(el)
  const dates = chartData.value.map((p) => p.date || "")
  const values = chartData.value.map((p) => p.value || 0)
  chartInstance.setOption({
    tooltip: { trigger: "axis" },
    grid: { left: "3%", right: "3%", bottom: "3%", containLabel: true },
    xAxis: { type: "category", data: dates, axisLabel: { fontSize: 11 } },
    yAxis: { type: "value", scale: true, axisLabel: { fontSize: 11 } },
    series: [{ type: "line", data: values, smooth: true, lineStyle: { color: "#e74c3c", width: 2 }, areaStyle: { color: "rgba(231,76,60,0.1)" } }],
  })
  window.addEventListener("resize", () => { if (chartInstance) chartInstance.resize() })
}

onMounted(loadStrategies)
onUnmounted(() => { if (chartInstance) { chartInstance.dispose(); chartInstance = null } })
</script>



