<template>
  <div>
    <h1 class="page-title">板块选股</h1>
    <div class="flex mb-2">
      <select v-model="sector" style="flex:1;padding:8px 14px;border:1px solid #ddd;border-radius:6px;font-size:14px;">
        <option value="">-- 选择板块 --</option>
        <option v-for="s in sectors" :key="s" :value="s">{{ s }}</option>
      </select>
      <button class="btn" @click="search">查询板块</button>
    </div>
    <div v-if="loading" class="loading">加载中...</div>
    <div v-if="error" class="error">{{ error }}</div>
    <div class="card" v-if="stocks.length">
      <div class="card-title">{{ sector }} - 成分股 ({{ stocks.length }})</div>
      <table>
        <tr><th>代码</th><th>名称</th><th>最新价</th><th>涨跌幅</th><th>成交量</th></tr>
        <tr v-for="s in sorted" :key="s.code||s.代码">
          <td>{{ s.code||s.代码 }}</td><td>{{ s.name||s.名称 }}</td>
          <td>{{ s.price||s.最新价||"--" }}</td>
          <td :class="(s.pct_chg||s.涨跌幅||0)>=0?'text-red':'text-green'">{{ s.涨跌幅||s.pct_chg||"--" }}</td>
          <td>{{ s.volume||s.成交量||"--" }}</td>
        </tr>
      </table>
    </div>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from "vue"
import api from "../api/index.js"
const sectors = ref([]); const sector = ref(""); const stocks = ref([]); const loading = ref(false); const error = ref("")
const sorted = computed(() => [...stocks.value].sort((a,b) => (b.涨跌幅||b.pct_chg||0) - (a.涨跌幅||a.pct_chg||0)))
onMounted(async () => { try { const r=await api.get("/sectors/list"); sectors.value=(r.data||[]).map(s=>s.板块名称||s.board_name||s.name) } catch(e) { error.value=e.message } })
async function search() {
  if (!sector.value) return; loading.value=true; error.value=""; stocks.value=[]
  try { const r=await api.get("/sectors/"+encodeURIComponent(sector.value)+"/stocks"); stocks.value=r.data||[]; if(!stocks.value.length) error.value="无数据" }
  catch(e) { error.value=e.message } finally { loading.value=false }
}
</script>
