<template>
  <div>
    <h1 class="page-title">持仓管理</h1>
    <div v-if="error" class="error">{{ error }}</div>
    <div class="flex gap-4 mb-2">
      <button :class="tab==='list'?'btn':''" :style="tab==='list'?'background:#e94560;color:#fff':'background:#fff;border:1px solid #ddd;color:#666'" @click="tab='list'">持仓列表</button>
      <button :class="tab==='add'?'btn':''" :style="tab==='add'?'background:#e94560;color:#fff':'background:#fff;border:1px solid #ddd;color:#666'" @click="tab='add'">添加持仓</button>
    </div>
    <div v-if="tab==='list'">
      <div v-if="holdings.length" class="card">
        <table><tr><th>代码</th><th>名称</th><th>持股数</th><th>成本价</th><th>买入日期</th><th>操作</th></tr>
        <tr v-for="h in holdings" :key="h.code">
          <td>{{ h.code }}</td><td>{{ h.name }}</td><td>{{ h.shares }}</td>
          <td>{{ Number(h.cost_price).toFixed(2) }}</td><td>{{ h.buy_date||"--" }}</td>
          <td><button class="btn" style="background:#e74c3c;padding:4px 12px;font-size:12px" @click="del(h.code)">删除</button></td>
        </tr></table>
      </div>
      <div v-else class="card empty">暂无持仓</div>
    </div>
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
import { ref, onMounted } from "vue"
import api from "../api/index.js"
const tab = ref("list"); const holdings = ref([]); const error = ref("")
const form = ref({ code:"", name:"", shares:100, cost_price:100, buy_date:new Date().toISOString().slice(0,10) })
async function load() { try { const r=await api.get("/portfolio/holdings"); holdings.value=r.data||[] } catch(e) { error.value=e.message } }
async function addHolding() {
  if (!form.value.code||!form.value.name) { error.value="代码和名称不能为空"; return }
  try { await api.post("/portfolio/holdings",form.value); form.value={code:"",name:"",shares:100,cost_price:100,buy_date:new Date().toISOString().slice(0,10)}; await load(); tab.value="list" }
  catch(e) { error.value=e.message }
}
async function del(code) { try { await api.delete("/portfolio/holdings/"+code); await load() } catch(e) { error.value=e.message } }
onMounted(load)
</script>
