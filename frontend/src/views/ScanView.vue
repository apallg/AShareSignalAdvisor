<template>
  <div>
    <h1 class="page-title">批量风险扫描</h1>
    <div v-if="error" class="error">{{ error }}</div>

    <div class="card">
      <div class="card-title">扫描配置</div>
      <div class="flex gap-4 mb-2" style="flex-wrap:wrap;">
        <label v-for="ds in dataSources" :key="ds.key" style="display:flex;align-items:center;gap:4px;font-size:13px;">
          <input type="checkbox" v-model="included[ds.key]" /> {{ ds.label }}
        </label>
      </div>
      <div class="flex mb-2">
        <label style="width:120px;">风险阈值: {{ threshold }}</label>
        <input type="range" v-model.number="threshold" min="1" max="10" style="flex:1;" />
      </div>
      <button class="btn" @click="scan" :disabled="scanning">{{ scanning ? "扫描中..." : "开始扫描" }}</button>
    </div>

    <div v-if="results.length" class="card">
      <div class="card-title">扫描结果 ({{ results.length }} 项)</div>
      <table>
        <tr><th>股票</th><th>风险等级</th><th>评分</th><th>风险点</th><th>建议</th></tr>
        <tr v-for="r in results" :key="r.stock_code">
          <td>{{ r.stock_name }}({{ r.stock_code }})</td>
          <td><span :class="['tag',r.risk_level==='高风险'?'tag-high':r.risk_level==='中风险'?'tag-mid':'tag-low']">{{ r.risk_level }}</span></td>
          <td>{{ r.risk_score }}/10</td>
          <td style="max-width:200px;font-size:12px;">{{ r.risk_detail?.slice(0,60)||"--" }}</td>
          <td style="max-width:150px;font-size:12px;">{{ r.suggestion?.slice(0,30)||"--" }}</td>
        </tr>
      </table>
    </div>
    <div v-else-if="scanned" class="card empty">扫描完成，无风险告警</div>
  </div>
</template>
<script setup>
import { ref, onMounted } from "vue"
import api from "../api/index.js"

const dataSources = [
  {key:"tech",label:"技术面"},{key:"capital",label:"资金面"},{key:"fundamental",label:"基本面"},
  {key:"news",label:"消息面"},{key:"market",label:"大盘环境"},
]
const included = ref({tech:true,capital:true,fundamental:true,news:true,market:true})
const threshold = ref(5)
const scanning = ref(false)
const scanned = ref(false)
const results = ref([])
const error = ref("")

async function scan() {
  scanning.value = true; error.value = ""; results.value = []; scanned.value = false
  try {
    const res = await api.post("/portfolio/scan", {threshold: threshold.value, include: included.value})
    results.value = res.data || []
    scanned.value = true
  } catch(e) {
    error.value = "扫描失败: " + (e.response?.data?.detail || e.message)
  }
  scanning.value = false
}
</script>
