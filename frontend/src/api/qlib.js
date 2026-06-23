import api from './index'

export default {
  syncData(full)           { return api.post('/qlib/data/sync', { full_resync: full }) },
  collectData(pool, retryMissing, forceTencent) {
    const body = { pool: pool || 'all' }
    if (retryMissing) body.retry_missing = true
    if (forceTencent) body.force_tencent = true
    return api.post('/qlib/data/collect', body)
  },
  getSyncStatus(id)        { return api.get(`/qlib/data/sync/${id}`) },
  getDataStatus()          { return api.get('/qlib/data/status') },
  getDataQuality()         { return api.get('/qlib/data/quality') },
  getModels()              { return api.get('/qlib/models') },
  trainModel(cfg)          { return api.post('/qlib/models/train', cfg) },
  getTrainStatus(id)       { return api.get(`/qlib/models/train/${id}`) },
  predict(cfg)             { return api.post('/qlib/models/predict', cfg) },
  runBacktest(cfg)         { return api.post('/qlib/backtest/run', cfg) },
  getExperiments()         { return api.get('/qlib/experiments') },
  getExperiment(id)        { return api.get(`/qlib/experiments/${id}`) },
  getTrainedModels()       { return api.get('/qlib/trained-models') },
}
