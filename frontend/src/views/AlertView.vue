<template>
  <div>
    <h1 class="page-title">风险告警</h1>
    <div v-if="error" class="error">{{ error }}</div>
    <div class="flex gap-4 mb-2">
      <div class="card flex-1 metric"><div class="value">{{ stats.high }}</div><div class="label">高风险</div></div>
      <div class="card flex-1 metric"><div class="value">{{ stats.mid }}</div><div class="label">中风险</div></div>
      <div class="card flex-1 metric"><div class="value">{{ stats.low }}</div><div class="label">低风险</div></div>
    </div>
    <div class="flex mb-2"><select v-model="levelFilter"><option value="">全部等级</option><option value="高风险">高风险</option><option value="中风险">中风险</option><option value="低风险">低风险</option></select></div>
    <div class="card" v-if="filtered.length">
      <table><tr><th>股票</th><th>等级</th><th>评分</th><th>时间</th></tr>
        <tr v-for="a in filtered" :key="a.id">
          <td>{{ a.stock_name }}({{ a.stock_code }})</td>
          <td><span :class="['tag', a.risk_level==='高风险'?'tag-high':a.risk_level==='中风险'?'tag-mid':'tag-low']">{{ a.risk_level }}</span></td>
          <td>{{ a.risk_score }}/10</td>
          <td style="white-space:nowrap">{{ a.created_at?.slice(0,16)||"--" }}</td>
        </tr>
      </table>
    </div>
    <div v-else class="card empty">暂无告警记录</div>
  </div>
</template>
<script setup>
import { ref, computed, onMounted } from "vue"
import api from "../api/index.js"
const alerts = ref([]); const stats = ref({high:0,mid:0,low:0}); const levelFilter = ref(""); const error = ref("")
const filtered = computed(() => !levelFilter.value ? alerts.value : alerts.value.filter(a=>a.risk_level===levelFilter.value))
onMounted(async () => {
  try {
    const [a,s] = await Promise.all([api.get("/alerts/?limit=100"), api.get("/alerts/stats?limit=200")])
    alerts.value = a.data||[]; stats.value = s.data||{high:0,mid:0,low:0}
  } catch(e) { error.value=e.message }
})
</script>
