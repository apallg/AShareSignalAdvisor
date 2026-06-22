<template>
  <div>
    <h1 class="page-title">
      交易面板
      <span v-if="!cashEnabled" style="font-size:12px;color:#e94560;font-weight:normal;">{{ brokerLabel }}</span>
    </h1>
    <div v-if="error" class="error">{{ error }}</div>

    <div class="grid-4 mb-2">
      <MetricCard :value="'¥' + Number(account.available || 0).toFixed(2)" label="可用资金" />
      <MetricCard :value="'¥' + Number(account.market_value || 0).toFixed(2)" label="持仓市值" />
      <MetricCard :value="'¥' + Number(account.total_assets || 0).toFixed(2)" label="总资产" />
      <MetricCard :value="'¥' + Number(account.unrealized_pnl || 0).toFixed(2)" label="未实现盈亏" :color="(account.unrealized_pnl || 0) >= 0 ? 'up' : 'down'" />
    </div>

    <div class="card">
      <div class="card-title">下单</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;">
        <div class="flex"><label style="width:60px;">代码</label><input v-model="orderForm.symbol" placeholder="600519" style="flex:1;" /></div>
        <div class="flex"><label style="width:60px;">名称</label><input v-model="orderForm.name" placeholder="贵州茅台" style="flex:1;" /></div>
        <div class="flex"><label style="width:60px;">方向</label>
          <select v-model="orderForm.side" style="flex:1;"><option value="buy">买入</option><option value="sell">卖出</option></select>
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:8px;">
        <div class="flex"><label style="width:60px;">数量</label><input v-model.number="orderForm.quantity" type="number" min="100" step="100" style="flex:1;" /></div>
        <div class="flex"><label style="width:60px;">类型</label>
          <select v-model="orderForm.price_type" style="flex:1;"><option value="market">市价单</option><option value="limit">限价单</option></select>
        </div>
        <div class="flex"><label style="width:60px;">限价</label><input v-model.number="orderForm.price" type="number" step="0.01" style="flex:1;" :disabled="orderForm.price_type==='market'" /></div>
      </div>
      <button class="btn" style="margin-top:12px;" @click="placeOrder" :disabled="submitting">
        {{ submitting ? '提交中...' : '下单' }}
      </button>
    </div>

    <DataTable
      title="委托列表"
      :rows="orders"
      :columns="orderColumns"
      empty-text="暂无委托"
    >
      <template #cell-side="{ value }">
        <span :class="value==='buy'?'text-red':'text-green'">{{ value==='buy'?'买入':'卖出' }}</span>
      </template>
      <template #cell-status="{ value }">
        <span :class="['tag', value==='filled'?'tag-low':value==='pending'?'tag-mid':value==='rejected'?'tag-high':'']">
          {{ {filled:'已成交',pending:'待成交',cancelled:'已撤销',rejected:'已拒绝'}[value] || value }}
        </span>
      </template>
      <template #cell-action="{ row }">
        <button v-if="row.status==='pending'" class="btn" style="background:#e74c3c;padding:4px 12px;font-size:12px;" @click="cancelOrder(row.id)">撤单</button>
      </template>
    </DataTable>

    <div class="grid-2 mb-2" style="grid-template-columns:1fr 1fr;">
      <div v-if="positions.length" class="card">
        <div class="card-title">持仓</div>
        <table>
          <thead>
            <tr><th>代码</th><th>数量</th><th>成本</th><th>现价</th><th>市值</th><th>盈亏</th></tr>
          </thead>
          <tbody>
            <tr v-for="p in positions" :key="p.symbol">
              <td>{{ p.symbol }}</td>
              <td>{{ p.shares }}</td>
              <td>{{ p.avg_cost }}</td>
              <td>{{ p.current_price }}</td>
              <td>{{ p.market_value }}</td>
              <td :class="p.unrealized_pnl >= 0 ? 'text-red' : 'text-green'">{{ p.unrealized_pnl >= 0 ? '+' : '' }}{{ p.unrealized_pnl }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="card empty">暂无持仓</div>

      <div v-if="trades.length" class="card">
        <div class="card-title">成交记录</div>
        <table>
          <thead>
            <tr><th>时间</th><th>代码</th><th>方向</th><th>价格</th><th>数量</th><th>金额</th></tr>
          </thead>
          <tbody>
            <tr v-for="t in trades.slice(0, 20)" :key="t.id">
              <td style="white-space:nowrap;">{{ t.trade_time?.slice(5,16) }}</td>
              <td>{{ t.symbol }}</td>
              <td :class="t.side==='buy'?'text-red':'text-green'">{{ t.side==='buy'?'买入':'卖出' }}</td>
              <td>{{ t.price }}</td>
              <td>{{ t.quantity }}</td>
              <td>{{ t.amount }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-else class="card empty">暂无成交</div>
    </div>
  </div>
</template>
<script setup>
import { ref, reactive, onMounted } from 'vue'
import api from '../api/index.js'
import MetricCard from '../components/MetricCard.vue'
import DataTable from '../components/DataTable.vue'
import { useBroker } from '../composables/useBroker.js'

const { cashEnabled, brokerLabel, loadBroker } = useBroker()

const error = ref('')
const submitting = ref(false)
const account = ref({})
const orders = ref([])
const trades = ref([])
const positions = ref([])

const orderForm = reactive({
  symbol: '600519', name: '', side: 'buy',
  quantity: 100, price_type: 'market', price: 0,
})

const orderColumns = [
  { key: 'symbol', label: '代码' },
  { key: 'side', label: '方向', tdClass: row => row.side === 'buy' ? 'text-red' : 'text-green' },
  { key: 'quantity', label: '数量' },
  { key: 'price_type', label: '类型', format: v => v === 'market' ? '市价' : '限价' },
  { key: 'price', label: '限价', format: v => Number(v) > 0 ? v : '--' },
  { key: 'filled_qty', label: '已成交' },
  { key: 'status', label: '状态' },
  { key: 'action', label: '操作', width: '80px' },
]

async function loadData() {
  try {
    const [a, o, t, p] = await Promise.all([
      api.get('/trading/account'),
      api.get('/trading/orders'),
      api.get('/trading/trades'),
      api.get('/trading/positions'),
    ])
    account.value = a.data || {}
    orders.value = o.data || []
    trades.value = t.data || []
    positions.value = p.data || []
  } catch (e) {
    error.value = e.message
  }
}

async function placeOrder() {
  if (!orderForm.symbol.trim()) { error.value = '请输入股票代码'; return }
  submitting.value = true; error.value = ''
  try {
    await api.post('/trading/orders', { ...orderForm })
    orderForm.name = ''; orderForm.price = 0
    await loadData()
  } catch (e) { error.value = e.message }
  submitting.value = false
}

async function cancelOrder(orderId) {
  try {
    await api.delete('/trading/orders/' + orderId)
    await loadData()
  } catch (e) { error.value = e.message }
}

onMounted(() => { loadBroker(); loadData() })
</script>
