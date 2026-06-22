<template>
  <div class="qlib-lab">
    <h1>Qlib 量化实验室</h1>
    <p class="subtitle">AI 模型训练、因子计算、精细化回测</p>

    <div class="tabs">
      <button v-for="t in tabs" :key="t.key" :class="{active: activeTab === t.key}" @click="activeTab = t.key">{{ t.label }}</button>
    </div>

    <!-- 数据同步 -->
    <section v-if="activeTab === 'data'" class="card">
      <h2>数据同步</h2>
      <div class="status-row"><span class="label">状态:</span>
        <span v-if="dataStatus.synced" class="badge green">已同步</span>
        <span v-else class="badge gray">未同步</span>
      </div>
      <div v-if="dataStatus.synced">
        <p>交易日: {{ dataStatus.dates }} 天 | 股票: {{ dataStatus.stocks }} 只</p>
        <p>范围: {{ dataStatus.first_date }} ~ {{ dataStatus.last_date }}</p>
      </div>
      <button @click="syncData(false)" :disabled="syncing" class="btn primary">{{ syncing ? '同步中...' : '增量同步' }}</button>
      <button @click="syncData(true)" :disabled="syncing" class="btn" style="margin-left:8px">全量同步</button>
      <p v-if="syncMsg" class="msg">{{ syncMsg }}</p>
    </section>

    <!-- 模型训练 -->
    <section v-if="activeTab === 'train'" class="card">
      <h2>模型训练</h2>
      <div class="form-grid">
        <label>模型: <select v-model="trainCfg.model_name">
          <option v-for="m in availableModels" :key="m.name" :value="m.name">{{ m.name }}</option>
        </select></label>
        <label>因子集: <select v-model="trainCfg.factor_set">
          <option>Alpha158</option><option>Alpha360</option>
        </select></label>
        <label>股票池: <select v-model="trainCfg.instruments">
          <option>csi300</option><option>csi500</option><option>all</option>
        </select></label>
        <label>训练开始: <input v-model="trainCfg.train_start" /></label>
        <label>训练结束: <input v-model="trainCfg.train_end" /></label>
        <label>验证结束: <input v-model="trainCfg.valid_end" /></label>
        <label>测试结束: <input v-model="trainCfg.test_end" /></label>
        <label>TopK: <input v-model.number="trainCfg.topk" type="number" /></label>
        <label>NDrop: <input v-model.number="trainCfg.n_drop" type="number" /></label>
      </div>
      <button @click="startTraining" :disabled="training" class="btn primary">{{ training ? '训练中...' : '开始训练' }}</button>
      <div v-if="trainResult" class="result-box">
        <p><strong>IC Mean:</strong> {{ trainResult.ic_mean }}</p>
        <p><strong>ICIR:</strong> {{ trainResult.icir }}</p>
        <div v-if="trainResult.backtest?.report">
          <h3>回测结果</h3>
          <div v-for="(metrics, key) in trainResult.backtest.report" :key="key">
            <h4>{{ key }}</h4>
            <table><tr v-for="(v, k) in metrics" :key="k"><td>{{ k }}</td><td>{{ v }}</td></tr></table>
          </div>
        </div>
      </div>
      <p v-if="trainError" class="msg error">{{ trainError }}</p>
    </section>

    <!-- 回测 -->
    <section v-if="activeTab === 'backtest'" class="card">
      <h2>独立回测</h2>
      <div class="form-grid">
        <label>TopK: <input v-model.number="backtestCfg.topk" type="number" /></label>
        <label>NDrop: <input v-model.number="backtestCfg.n_drop" type="number" /></label>
        <label>开始: <input v-model="backtestCfg.start_time" /></label>
        <label>结束: <input v-model="backtestCfg.end_time" /></label>
      </div>
      <button @click="runBacktest" :disabled="backtesting" class="btn primary">{{ backtesting ? '回测中...' : '运行回测' }}</button>
      <div v-if="backtestResult" class="result-box">
        <div v-for="(metrics, key) in backtestResult.report" :key="key">
          <h4>{{ key }}</h4>
          <table><tr v-for="(v, k) in metrics" :key="k"><td>{{ k }}</td><td>{{ v }}</td></tr></table>
        </div>
      </div>
    </section>

    <!-- 实验 -->
    <section v-if="activeTab === 'experiments'" class="card">
      <h2>实验记录</h2>
      <button @click="loadExperiments" class="btn">刷新</button>
      <ul><li v-for="e in experiments" :key="e.id">{{ e.name }} (ID: {{ e.id }})</li></ul>
    </section>
  </div>
</template>

<script>
import qlibApi from '../api/qlib'

export default {
  name: 'QlibLab',
  data: () => ({
    activeTab: 'data',
    tabs: [
      { key: 'data', label: '数据同步' },
      { key: 'train', label: '模型训练' },
      { key: 'backtest', label: '回测' },
      { key: 'experiments', label: '实验记录' },
    ],
    dataStatus: { synced: false },
    syncing: false, syncMsg: '',
    availableModels: [],
    trainCfg: {
      model_name: 'lightgbm', factor_set: 'Alpha158', instruments: 'csi300',
      train_start: '2018-01-01', train_end: '2021-12-31',
      valid_start: '2022-01-01', valid_end: '2022-12-31',
      test_start: '2023-01-01', test_end: '2024-12-31',
      topk: 50, n_drop: 5
    },
    training: false, trainResult: null, trainError: '',
    backtestCfg: { topk: 50, n_drop: 5, start_time: '2023-01-01', end_time: '2024-12-31' },
    backtesting: false, backtestResult: null,
    experiments: [],
  }),
  mounted() {
    this.loadDataStatus()
    this.loadModels()
  },
  methods: {
    async loadDataStatus() {
      try {
        const r = await qlibApi.getDataStatus()
        if (r?.data) this.dataStatus = r.data
      } catch(e) { console.log('qlib data status 获取失败') }
    },
    async loadModels() {
      try {
        const r = await qlibApi.getModels()
        if (r?.data) this.availableModels = r.data
      } catch(e) { console.log('qlib models 获取失败') }
    },
    async syncData(full) {
      this.syncing = true; this.syncMsg = ''
      try {
        const r = await qlibApi.syncData(full)
        this.syncMsg = `任务已启动: ${r.data.job_id}`
        setTimeout(() => this.loadDataStatus(), 3000)
      } catch(e) { this.syncMsg = '同步失败: ' + e.message }
      this.syncing = false
    },
    async startTraining() {
      this.training = true; this.trainResult = null; this.trainError = ''
      try {
        const r = await qlibApi.trainModel(this.trainCfg)
        const jobId = r.data.job_id
        this.trainError = `训练已启动: ${jobId}，轮询中...`
        await this._pollTrainJob(jobId)
        const job = await qlibApi.getTrainStatus(jobId)
        if (job.data.status === 'done') {
          this.trainResult = job.data.result
        } else {
          this.trainError = job.data.error || '训练失败'
        }
      } catch(e) { this.trainError = e.message }
      this.training = false
    },
    async _pollTrainJob(jobId) {
      for (let i = 0; i < 120; i++) {
        await new Promise(r => setTimeout(r, 5000))
        try {
          const r = await qlibApi.getTrainStatus(jobId)
          if (r.data.data.status !== 'running') return
        } catch(e) { return }
      }
    },
    async runBacktest() {
      this.backtesting = true; this.backtestResult = null
      try {
        const r = await qlibApi.runBacktest(this.backtestCfg)
        this.backtestResult = r.data.data
      } catch(e) { console.error(e) }
      this.backtesting = false
    },
    async loadExperiments() {
      try { const r = await qlibApi.getExperiments(); this.experiments = r.data.data } catch(e) {}
    },
  },
}
</script>

<style scoped>
.qlib-lab { max-width: 960px; margin: 0 auto; padding: 20px; }
.subtitle { color: #888; margin-bottom: 20px; }
.tabs { display: flex; gap: 8px; margin-bottom: 20px; }
.tabs button { padding: 8px 20px; border: 1px solid #ddd; background: #f8f8f8; border-radius: 6px; cursor: pointer; }
.tabs button.active { background: #1a73e8; color: #fff; border-color: #1a73e8; }
.card { background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.1); margin-bottom: 16px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }
.form-grid label { display: flex; flex-direction: column; font-size: 14px; color: #555; }
.form-grid input, .form-grid select { padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px; margin-top: 4px; }
.btn { padding: 8px 20px; border: 1px solid #ccc; background: #fff; border-radius: 6px; cursor: pointer; }
.btn.primary { background: #1a73e8; color: #fff; border-color: #1a73e8; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px; }
.badge.green { background: #e8f5e9; color: #2e7d32; }
.badge.gray { background: #eee; color: #666; }
.msg { margin-top: 10px; padding: 8px; background: #f0f7ff; border-radius: 4px; }
.msg.error { background: #fff0f0; color: #c62828; }
.result-box { margin-top: 16px; padding: 16px; background: #f8f9fa; border-radius: 6px; }
.result-box table { width: 100%; border-collapse: collapse; }
.result-box td { padding: 4px 8px; border-bottom: 1px solid #eee; }
.status-row { margin-bottom: 10px; }
</style>
