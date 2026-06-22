<template>
  <div>
    <h1 class="page-title">持仓管理</h1>
    <div v-if="error" class="error">{{ error }}</div>

    <!-- 账户总览 -->
    <div class="grid-4 mb-2">
      <MetricCard :value="'¥' + Number(account.available || 0).toFixed(2)" label="可用资金" />
      <MetricCard :value="'¥' + Number(account.market_value || 0).toFixed(2)" label="持仓市值" />
      <MetricCard :value="'¥' + Number(account.total_assets || 0).toFixed(2)" label="总资产" />
      <MetricCard :value="'¥' + Number(account.unrealized_pnl || 0).toFixed(2)" label="未实现盈亏" :color="(account.unrealized_pnl || 0) >= 0 ? 'up' : 'down'" />
    </div>

    <!-- 资金管理 -->
    <div class="card" style="margin-bottom:16px;">
      <div class="card-title">
        资金管理
        <span v-if="!cashEnabled" style="font-size:11px;color:#e94560;margin-left:8px;">{{ brokerLabel }} · 不可操作</span>
      </div>
      <div v-if="cashEnabled" style="display:flex;gap:8px;align-items:flex-end;flex-wrap:wrap;">
        <div class="flex" style="flex-direction:column;">
          <label style="font-size:11px;color:#999;margin-bottom:4px;">金额</label>
          <input v-model.number="cashAmount" type="number" min="0" step="1000" style="width:150px;" placeholder="金额" />
        </div>
        <button class="btn" style="background:#27ae60;" @click="addCash">充值</button>
        <button class="btn" style="background:#e67e22;" @click="setCash">设为</button>
        <button class="btn" style="background:#e74c3c;" @click="withdrawCash">出金</button>
      </div>
      <div style="font-size:12px;color:#999;margin-top:8px;">
        现金: ¥{{ Number(account.cash || 0).toFixed(2) }} &nbsp; 冻结: ¥{{ Number(account.frozen || 0).toFixed(2) }}
        <span v-if="!cashEnabled" style="margin-left:8px;color:#e94560;">(来自 {{ brokerLabel }}，不可修改)</span>
      </div>
    </div>

    <!-- 持仓切换 -->
    <div class="flex gap-4 mb-2">
      <button :style="tabStyle('list')" @click="tab='list'">持仓列表</button>
      <button :style="tabStyle('add')" @click="tab='add'">添加持仓</button>
    </div>

    <template v-if="tab==='list'">
      <div v-if="holdings.length" class="card">
        <table>
          <thead>
            <tr><th>代码</th><th>名称</th><th>持股数</th><th>成本价</th><th>买入日期</th><th>操作</th></tr>
          </thead>
          <tbody>
            <tr v-for="h in holdings" :key="h.code">
            <td>{{ h.code }}</td><td>{{ h.name }}</td><td>{{ h.shares }}</td>
            <td>{{ Number(h.cost_price).toFixed(2) }}</td><td>{{ h.buy_date || '--' }}</td>
            <td><button class="btn" style="background:#e74c3c;padding:4px 12px;font-size:12px" @click="del(h.code)">删除</button></td>
          </tr>
            </tbody>
        </table>
      </div>
      <div v-else class="card empty">暂无持仓</div>
    </template>

    <div v-if="tab==='add'" class="card" style="max-width:400px">
      <div class="card-title">新增持仓</div>
      <div class="flex mb-2"><label style="width:80px">股票代码</label><input v-model="form.code" placeholder="600519" style="flex:1" /></div>
      <div class="flex mb-2"><label style="width:80px">名称</label><input v-model="form.name" placeholder="贵州茅台" style="flex:1" /></div>
      <div class="flex mb-2"><label style="width:80px">数量</label><input v-model.number="form.shares" type="number" min="1" style="flex:1" /></div>
      <div class="flex mb-2"><label style="width:80px">成本价</label><input v-model="form.cost_price" type="text" style="flex:1" placeholder="如 100.50" /></div>
      <div class="flex mb-2"><label style="width:80px">买入日期</label><input v-model="form.buy_date" type="date" style="flex:1" /></div>
      <button class="btn w-full mt-2" @click="addHolding">添加</button>
    </div>
  </div>
</template>
<script setup>
import { ref, onMounted } from 'vue'
import api from '../api/index.js'
import MetricCard from '../components/MetricCard.vue'
import { useBroker } from '../composables/useBroker.js'

const { cashEnabled, brokerLabel, loadBroker } = useBroker()

const tab = ref('list')
const holdings = ref([])
const account = ref({})
const cashAmount = ref(10000)
const error = ref('')
const form = ref({ code: '', name: '', shares: 100, cost_price: 100, buy_date: new Date().toISOString().slice(0, 10) })

const tabStyle = (name) => tab.value === name
  ? 'background:#e94560;color:#fff;border:none;border-radius:6px;padding:8px 20px;cursor:pointer;font-size:14px;'
  : 'background:#fff;border:1px solid #ddd;color:#666;border-radius:6px;padding:8px 20px;cursor:pointer;font-size:14px;'

async function loadAccount() {
  try { const r = await api.get('/trading/account'); account.value = r.data || {} }
  catch (e) { error.value = e.message }
}
async function load() {
  try { const r = await api.get('/portfolio/holdings'); holdings.value = r.data || [] }
  catch (e) { error.value = e.message }
}
async function addHolding() {
  if (!form.value.code || !form.value.name) { error.value = '代码和名称不能为空'; return }
  try {
    await api.post('/portfolio/holdings', form.value)
    form.value = { code: '', name: '', shares: 100, cost_price: 100, buy_date: new Date().toISOString().slice(0, 10) }
    await load(); tab.value = 'list'
  } catch (e) { error.value = e.message }
}
async function del(code) {
  try { await api.delete('/portfolio/holdings/' + code); await load() }
  catch (e) { error.value = e.message }
}

async function addCash() {
  if (!cashAmount.value || cashAmount.value <= 0) { error.value = '请输入有效金额'; return }
  try { await api.post('/trading/account/cash', { amount: cashAmount.value }); await loadAccount(); error.value = '' }
  catch (e) { error.value = e.message }
}
async function setCash() {
  if (cashAmount.value < 0) { error.value = '金额不能为负'; return }
  try { await api.put('/trading/account/cash', { amount: cashAmount.value }); await loadAccount(); error.value = '' }
  catch (e) { error.value = e.message }
}
async function withdrawCash() {
  if (!cashAmount.value || cashAmount.value <= 0) { error.value = '请输入有效金额'; return }
  try { await api.post('/trading/account/withdraw', { amount: cashAmount.value }); await loadAccount(); error.value = '' }
  catch (e) { error.value = e.message }
}

onMounted(() => { loadBroker(); loadAccount(); load() })
</script>
