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

      <!-- 一键更新：采集 + 增量同步 -->
      <div style="margin-bottom: 16px">
        <div style="display:flex; align-items:center; gap:10px; flex-wrap:wrap">
          <button @click="collectAndSync" :disabled="syncing" class="btn primary" style="background:#2e7d32; border-color:#2e7d32">
            {{ syncing ? '更新中...' : '一键更新到最新' }}
          </button>
          <select v-model="collectPool" style="padding:6px 10px; border:1px solid #ccc; border-radius:4px">
            <option value="all">全部A股 (~5500只)</option>
            <option value="csi_all">沪深300+中证500 (~800只)</option>
            <option value="csi300">仅沪深300</option>
            <option value="csi500">仅中证500</option>
          </select>
        </div>
        <p style="font-size:12px; color:#888; margin-top:6px">
          采集最新行情 → MySQL → 自动增量同步 → qlib可用
          <template v-if="collectPool === 'all'">⚠ 全A股首次采集耗时长(数小时)，日常增量仅需几分钟</template>
        </p>
      </div>
      <p v-if="syncMsg" class="msg" :class="{ error: syncError }">{{ syncMsg }}</p>

      <!-- 数据质量 -->
      <div style="margin-top: 16px">
        <button @click="loadDataQuality" :disabled="loadingQuality" class="btn" style="margin-bottom:10px">
          {{ loadingQuality ? '检查中...' : '数据质量检查' }}
        </button>
        <div v-if="dataQuality" class="quality-grid">
          <div class="q-item">
            <span class="q-num">{{ dataQuality.total_stocks || 0 }}</span>
            <span class="q-label">已采集股票</span>
          </div>
          <div class="q-item good">
            <span class="q-num">{{ dataQuality.good_records || 0 }}</span>
            <span class="q-label">完整 (≥500条)</span>
          </div>
          <div class="q-item warn">
            <span class="q-num">{{ dataQuality.short_records || 0 }}</span>
            <span class="q-label">不足 (&lt;100条)</span>
          </div>
          <div class="q-item bad">
            <span class="q-num">{{ dataQuality.missing_stocks || 0 }}</span>
            <span class="q-label">完全缺失</span>
          </div>
        </div>
        <div v-if="dataQuality && dataQuality.worst && dataQuality.worst.length" style="margin-top:10px">
          <p style="font-size:13px; color:#888; margin-bottom:4px">数据最少的股票 (前20):</p>
          <div style="display:flex; flex-wrap:wrap; gap:4px">
            <span v-for="s in dataQuality.worst" :key="s.code" class="stock-tag" :class="s.status">
              {{ s.code }} ({{ s.records }}条)
            </span>
          </div>
        </div>
        <button v-if="dataQuality && dataQuality.short_records > 0" @click="retryMissingData" :disabled="syncing" class="btn" style="margin-top:10px; background:#e65100; border-color:#e65100; color:#fff">
          {{ syncing ? '补采中...' : `补采 ${dataQuality.short_records} 只缺失股票 (Tencent, ~640天/只)` }}
        </button>
      </div>

      <div class="divider"><span>或手动操作</span></div>

      <button @click="syncData(false)" :disabled="syncing" class="btn primary">增量同步</button>
      <button @click="syncData(true)" :disabled="syncing" class="btn" style="margin-left:8px">全量同步</button>
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
          <option>csi300</option><option>csi500</option><option>all</option><option value="a500">全部≥500条 (5034只)</option>
        </select></label>
        <label>训练开始: <input v-model="trainCfg.train_start" /></label>
        <label>训练结束: <input v-model="trainCfg.train_end" /></label>
        <label>验证开始: <input v-model="trainCfg.valid_start" /></label>
        <label>验证结束: <input v-model="trainCfg.valid_end" /></label>
        <label>测试开始: <input v-model="trainCfg.test_start" /></label>
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

    <!-- 已训练模型（核心新增） -->
    <section v-if="activeTab === 'trained'" class="card">
      <h2>已训练模型</h2>
      <button @click="loadTrainedModels" :disabled="loadingModels" class="btn primary" style="margin-bottom:16px">
        {{ loadingModels ? '加载中...' : '刷新列表' }}
      </button>

      <div v-if="trainedModels.length === 0 && !loadingModels" class="msg">暂无已训练模型，请先在"模型训练"页签中训练。</div>

      <div v-for="m in trainedModels" :key="m.run_id" class="model-card">
        <div class="model-header">
          <span class="model-name">{{ m.model_class || '未知模型' }}</span>
          <span class="badge green" v-if="m.ic !== null">IC {{ (m.ic * 100).toFixed(2) }}%</span>
          <span class="badge gray" v-else>无IC</span>
          <span class="badge" v-if="m.icir !== null">ICIR {{ m.icir.toFixed(2) }}</span>
        </div>
        <div class="model-meta">
          <span>因子: {{ m.factor_set || '-' }}</span>
          <span>股票池: {{ m.instruments || '-' }}</span>
          <span>训练: {{ m.train_period || '-' }}</span>
          <span>测试: {{ m.test_period || '-' }}</span>
          <span>实验: {{ m.experiment_name }}</span>
        </div>
        <button @click="selectModel(m)" class="btn primary" style="margin-top:8px">
          {{ selectedModel?.run_id === m.run_id ? '已选中' : '使用此模型' }}
        </button>
      </div>
    </section>

    <!-- 模型预测 -->
    <section v-if="activeTab === 'predict'" class="card">
      <h2>模型预测</h2>

      <div v-if="!selectedModel" class="msg">
        请先在「已训练模型」页签中选择一个模型。
        <button @click="activeTab = 'trained'" class="btn" style="margin-left:8px">去选择</button>
      </div>

      <div v-if="selectedModel">
        <div class="selected-model-info">
          <strong>当前模型:</strong> {{ selectedModel.model_class }} |
          IC: {{ selectedModel.ic !== null ? (selectedModel.ic * 100).toFixed(2) + '%' : '-' }} |
          {{ selectedModel.factor_set }} | {{ selectedModel.instruments }}
        </div>

        <div class="form-grid" style="margin-top:16px">
          <label>股票池: <select v-model="predictCfg.instruments">
            <option>csi300</option><option>csi500</option><option>all</option><option value="a500">全部≥500条 (5034只)</option>
          </select></label>
          <label>TopK: <input v-model.number="predictCfg.topk" type="number" /></label>
          <label>开始日期: <input v-model="predictCfg.start_time" /></label>
          <label>结束日期: <input v-model="predictCfg.end_time" /></label>
        </div>

        <button @click="runPrediction" :disabled="predicting" class="btn primary">
          {{ predicting ? '预测中...' : '生成预测' }}
        </button>
        <p v-if="predictError" class="msg error">{{ predictError }}</p>

        <div v-if="predictResult" class="result-box" style="margin-top:16px">
          <h3>预测结果 (共 {{ predictResult.count }} 条)</h3>
          <div v-if="predictResult.by_date">
            <div v-for="(stocks, date) in predictResult.by_date" :key="date" style="margin-bottom:20px">
              <h4>{{ date }} (Top {{ stocks.length }} 只)</h4>
              <table class="pred-table">
                <thead><tr><th>股票</th><th>评分</th></tr></thead>
                <tbody>
                  <tr v-for="s in stocks" :key="s.instrument">
                    <td>{{ s.instrument }}</td>
                    <td :class="s.score > 0 ? 'positive' : 'negative'">{{ s.score.toFixed(6) }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
          <div v-else>
            <p>无按日期分组的预测数据</p>
          </div>
        </div>
      </div>
    </section>

    <!-- 独立回测 -->
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

    <!-- 实验概览 -->
    <section v-if="activeTab === 'experiments'" class="card">
      <h2>实验概览</h2>
      <button @click="loadExperiments" class="btn primary" style="margin-bottom:16px">刷新</button>
      <div v-for="exp in experiments" :key="exp.id" class="model-card" @click="toggleExperiment(exp)" style="cursor:pointer">
        <div class="model-header">
          <span class="model-name">{{ exp.name }}</span>
          <span class="badge gray">ID: {{ exp.id }}</span>
        </div>
        <div v-if="exp.runs && expandedExperiments[exp.id]" style="margin-top:10px">
          <div v-for="run in exp.runs" :key="run.run_id" class="run-item">
            <span>{{ run.run_id.slice(0, 8) }}...</span>
            <span v-if="run.metrics.IC">IC: {{ (run.metrics.IC * 100).toFixed(2) }}%</span>
            <span v-if="run.metrics.ICIR">ICIR: {{ run.metrics.ICIR.toFixed(2) }}</span>
            <span v-if="run.has_model" class="badge green">有模型</span>
          </div>
        </div>
      </div>
    </section>
  </div>
</template>

<script>
import qlibApi from '../api/qlib'

export default {
  name: 'QlibLab',
  data: () => ({
    activeTab: 'trained',
    tabs: [
      { key: 'data', label: '数据同步' },
      { key: 'train', label: '模型训练' },
      { key: 'trained', label: '已训练模型' },
      { key: 'predict', label: '模型预测' },
      { key: 'backtest', label: '独立回测' },
      { key: 'experiments', label: '实验概览' },
    ],
    // 数据同步
    dataStatus: { synced: false },
    syncing: false, syncMsg: '', syncError: false,
    collectPool: 'all',
    dataQuality: null, loadingQuality: false,
    // 模型训练
    availableModels: [],
    trainCfg: {
      model_name: 'lightgbm', factor_set: 'Alpha158', instruments: 'csi300',
      train_start: '2018-01-01', train_end: '2021-12-31',
      valid_start: '2022-01-01', valid_end: '2022-12-31',
      test_start: '2023-01-01', test_end: '2024-12-31',
      topk: 50, n_drop: 5
    },
    training: false, trainResult: null, trainError: '',
    // 已训练模型
    trainedModels: [],
    loadingModels: false,
    selectedModel: null,
    // 模型预测
    predictCfg: { instruments: 'csi300', start_time: '2024-06-01', end_time: '2024-12-31', topk: 30 },
    predicting: false, predictResult: null, predictError: '',
    // 独立回测
    backtestCfg: { topk: 50, n_drop: 5, start_time: '2023-01-01', end_time: '2024-12-31' },
    backtesting: false, backtestResult: null,
    // 实验概览
    experiments: [],
    expandedExperiments: {},
  }),
  mounted() {
    this.loadDataStatus()
    this.loadDataQuality()
    this.loadModels()
    this.loadTrainedModels()
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
      this.syncing = true; this.syncMsg = ''; this.syncError = false
      try {
        const r = await qlibApi.syncData(full)
        const d = r.data
        if (d.status === 'done') {
          const res = d.result || {}
          this.syncMsg = `同步完成: ${res.new_dates || 0} 个新交易日, 共 ${res.dates || '?'} 天, ${res.stocks || '?'} 只股票`
          if (res.message) this.syncMsg = res.message
          this.loadDataStatus()
        } else {
          const jobId = d.job_id
          this.syncMsg = `全量同步已启动 (${jobId})，预计 2-3 分钟...`
          await this._pollSyncJob(jobId)
          const job = await qlibApi.getSyncStatus(jobId)
          if (job.data.status === 'done') {
            const res = job.data.result || {}
            this.syncMsg = `全量同步完成: ${res.dates || '?'} 个交易日, ${res.stocks || '?'} 只股票`
          } else {
            this.syncMsg = job.data.error || '同步失败'
            this.syncError = true
          }
          this.loadDataStatus()
        }
      } catch(e) {
        this.syncMsg = '同步失败: ' + e.message
        this.syncError = true
      }
      this.syncing = false
    },
    async collectAndSync() {
      this.syncing = true; this.syncMsg = ''; this.syncError = false
      try {
        const r = await qlibApi.collectData(this.collectPool)
        const d = r.data

        // 数据已是最新，无需采集和轮询
        if (d.status === 'done') {
          this.syncMsg = d.message || '数据已是最新'
          this.loadDataStatus()
          this.syncing = false
          return
        }

        const jobId = d.job_id
        this.syncMsg = d.message || `采集已启动: ${jobId}`

        // 轮询采集进度 (最多等 2 小时，全 A 股首次采集可能需要较长时间)
        for (let i = 0; i < 1200; i++) {
          await new Promise(res => setTimeout(res, 3000))
          const job = await qlibApi.getSyncStatus(jobId)
          const status = job.data.status
          this.syncMsg = job.data.message || status
          if (status === 'done') {
            this.loadDataStatus()
            this.loadDataQuality()
            const coll = job.data.collect || {}
            const sync = job.data.sync || {}
            const recommend = job.data.recommend || ''
            this.syncMsg = `更新完成! 采集 ${coll.success}/${coll.total} 只股票, 新增 ${sync.new_dates || 0} 个交易日`
            if (recommend) this.syncMsg += '。' + recommend
            break
          } else if (status === 'error') {
            this.syncMsg = job.data.error || '采集失败'
            this.syncError = true
            break
          }
        }
      } catch(e) {
        this.syncMsg = '更新失败: ' + e.message
        this.syncError = true
      }
      this.syncing = false
    },
    async retryMissingData() {
      this.syncing = true; this.syncMsg = ''; this.syncError = false
      try {
        const r = await qlibApi.collectData('all', true, false)
        const d = r.data
        if (d.status === 'done') {
          this.syncMsg = d.message || '没有缺数据的股票'
          this.syncing = false
          return
        }
        const jobId = d.job_id
        this.syncMsg = d.message
        for (let i = 0; i < 600; i++) {
          await new Promise(res => setTimeout(res, 2000))
          const job = await qlibApi.getSyncStatus(jobId)
          const status = job.data.status
          this.syncMsg = job.data.message || status
          if (status === 'done') {
            this.loadDataStatus()
            this.loadDataQuality()
            const coll = job.data.collect || {}
            const sync = job.data.sync || {}
            this.syncMsg = `补采完成! 成功 ${coll.success}/${coll.total} 只股票, 新增 ${sync.new_dates || 0} 个交易日`
            break
          } else if (status === 'error') {
            this.syncMsg = job.data.error || '补采失败'
            this.syncError = true
            break
          }
        }
      } catch(e) {
        this.syncMsg = '补采失败: ' + e.message
        this.syncError = true
      }
      this.syncing = false
    },
    async _pollSyncJob(jobId) {
      for (let i = 0; i < 60; i++) {
        await new Promise(r => setTimeout(r, 3000))
        try {
          const r = await qlibApi.getSyncStatus(jobId)
          if (r.data.data.status !== 'running') return
        } catch(e) { return }
      }
    },
    async startTraining() {
      this.training = true; this.trainResult = null; this.trainError = ''
      const startTime = Date.now()
      try {
        const r = await qlibApi.trainModel(this.trainCfg)
        const jobId = r.data.job_id
        this.trainError = `训练已启动: ${jobId}，轮询中...`
        // 最多等 2 小时 (720 * 10s)
        for (let i = 0; i < 720; i++) {
          await new Promise(res => setTimeout(res, 10000))
          try {
            const job = await qlibApi.getTrainStatus(jobId)
            const status = job.data.status
            const elapsed = Math.floor((Date.now() - startTime) / 60000)
            if (status === 'done') {
              this.trainResult = job.data.result
              this.trainError = ''
              this.loadTrainedModels()
              break
            } else if (status === 'error') {
              this.trainError = job.data.error || '训练失败'
              break
            } else {
              this.trainError = `训练中... (${elapsed}分钟) ${job.data.result?.message || ''}`
            }
          } catch(e) {
            this.trainError = `轮询中... (网络抖动，继续等待)`
          }
        }
        if (!this.trainResult && !this.trainError.includes('训练失败')) {
          this.trainError = '训练超时 (2小时)，任务仍在后台运行，稍后可查看结果'
        }
      } catch(e) { this.trainError = '启动失败: ' + (e.message || e) }
      this.training = false
    },
    // 已训练模型
    async loadTrainedModels() {
      this.loadingModels = true
      try {
        const r = await qlibApi.getTrainedModels()
        if (r?.data) this.trainedModels = r.data
      } catch(e) {
        console.error('加载已训练模型失败', e)
      }
      this.loadingModels = false
    },
    selectModel(model) {
      if (this.selectedModel?.run_id === model.run_id) {
        this.selectedModel = null
      } else {
        this.selectedModel = model
        this.predictCfg.instruments = model.instruments || 'csi300'
        this.activeTab = 'predict'
      }
    },
    // 模型预测
    async runPrediction() {
      if (!this.selectedModel) {
        this.predictError = '请先选择一个已训练模型'
        return
      }
      this.predicting = true; this.predictResult = null; this.predictError = ''
      try {
        const r = await qlibApi.predict({
          experiment_id: this.selectedModel.experiment_id,
          run_id: this.selectedModel.run_id,
          instruments: this.predictCfg.instruments,
          start_time: this.predictCfg.start_time,
          end_time: this.predictCfg.end_time,
          topk: this.predictCfg.topk,
        })
        if (r?.data) this.predictResult = r.data
      } catch(e) {
        this.predictError = '预测失败: ' + (e.response?.data?.detail || e.message)
      }
      this.predicting = false
    },
    // 独立回测
    async runBacktest() {
      this.backtesting = true; this.backtestResult = null
      try {
        const r = await qlibApi.runBacktest(this.backtestCfg)
        this.backtestResult = r.data.data
      } catch(e) { console.error(e) }
      this.backtesting = false
    },
    // 实验概览
    async loadExperiments() {
      try {
        const r = await qlibApi.getExperiments()
        const exps = r.data.data || []
        for (const exp of exps) {
          try {
            const detail = await qlibApi.getExperiment(exp.id)
            exp.runs = detail.data?.runs || []
          } catch(e) { exp.runs = [] }
        }
        this.experiments = exps
      } catch(e) { console.error(e) }
    },
    toggleExperiment(exp) {
      this.expandedExperiments[exp.id] = !this.expandedExperiments[exp.id]
    },
    async loadDataQuality() {
      this.loadingQuality = true
      try {
        const r = await qlibApi.getDataQuality()
        if (r?.data) this.dataQuality = r.data
      } catch(e) { console.error(e) }
      this.loadingQuality = false
    },
  },
}
</script>

<style scoped>
.qlib-lab { max-width: 960px; margin: 0 auto; padding: 20px; }
.subtitle { color: #888; margin-bottom: 20px; }
.tabs { display: flex; gap: 8px; margin-bottom: 20px; flex-wrap: wrap; }
.tabs button { padding: 8px 20px; border: 1px solid #ddd; background: #f8f8f8; border-radius: 6px; cursor: pointer; }
.tabs button.active { background: #1a73e8; color: #fff; border-color: #1a73e8; }
.card { background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.1); margin-bottom: 16px; }
.form-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; margin-bottom: 16px; }
.form-grid label { display: flex; flex-direction: column; font-size: 14px; color: #555; }
.form-grid input, .form-grid select { padding: 6px 10px; border: 1px solid #ccc; border-radius: 4px; margin-top: 4px; }
.btn { padding: 8px 20px; border: 1px solid #ccc; background: #fff; border-radius: 6px; cursor: pointer; }
.btn.primary { background: #1a73e8; color: #fff; border-color: #1a73e8; }
.btn:disabled { opacity: .5; cursor: not-allowed; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px; margin-left: 6px; }
.badge.green { background: #e8f5e9; color: #2e7d32; }
.badge.gray { background: #eee; color: #666; }
.msg { margin-top: 10px; padding: 8px; background: #f0f7ff; border-radius: 4px; }
.msg.error { background: #fff0f0; color: #c62828; }
.result-box { margin-top: 16px; padding: 16px; background: #f8f9fa; border-radius: 6px; }
.result-box table { width: 100%; border-collapse: collapse; }
.result-box td { padding: 4px 8px; border-bottom: 1px solid #eee; }
.status-row { margin-bottom: 10px; }

/* 已训练模型卡片 */
.model-card { border: 1px solid #e0e0e0; border-radius: 8px; padding: 14px; margin-bottom: 12px; }
.model-card:hover { border-color: #1a73e8; }
.model-header { display: flex; align-items: center; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.model-name { font-size: 16px; font-weight: 600; }
.model-meta { display: flex; gap: 16px; font-size: 13px; color: #666; flex-wrap: wrap; }

/* 已选中模型提示 */
.selected-model-info { padding: 10px 14px; background: #e8f0fe; border-radius: 6px; font-size: 14px; }

/* 预测结果表格 */
.pred-table { width: 100%; border-collapse: collapse; margin-top: 8px; }
.pred-table th { background: #f0f0f0; padding: 6px 10px; text-align: left; font-size: 13px; }
.pred-table td { padding: 4px 10px; border-bottom: 1px solid #eee; font-size: 13px; }
.pred-table .positive { color: #c62828; }
.pred-table .negative { color: #2e7d32; }

.run-item { display: flex; gap: 12px; padding: 6px 10px; background: #f8f9fa; border-radius: 4px; margin-bottom: 4px; font-size: 13px; align-items: center; }
.divider { margin: 16px 0; text-align: center; border-top: 1px solid #eee; }
.divider span { position: relative; top: -10px; background: #fff; padding: 0 12px; color: #999; font-size: 13px; }
.quality-grid { display: flex; gap: 12px; flex-wrap: wrap; }
.q-item { flex: 1; min-width: 100px; text-align: center; padding: 12px 8px; background: #f8f9fa; border-radius: 8px; }
.q-item.good { background: #e8f5e9; }
.q-item.warn { background: #fff8e1; }
.q-item.bad { background: #ffebee; }
.q-num { display: block; font-size: 24px; font-weight: 700; }
.q-label { display: block; font-size: 12px; color: #888; margin-top: 4px; }
.stock-tag { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 12px; background: #eee; }
.stock-tag.short { background: #fff8e1; color: #e65100; }
.stock-tag.empty { background: #ffebee; color: #c62828; }
.stock-tag.good { background: #e8f5e9; color: #2e7d32; }
</style>
