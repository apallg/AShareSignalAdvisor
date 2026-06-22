import api from './index'

export default {
  syncData(full)           { return api.post('/qlib/data/sync', { full_resync: full }) },
  getDataStatus()          { return api.get('/qlib/data/status') },
  getModels()              { return api.get('/qlib/models') },
  trainModel(cfg)          { return api.post('/qlib/models/train', cfg) },
  getTrainStatus(id)       { return api.get(`/qlib/models/train/${id}`) },
  predict(cfg)             { return api.post('/qlib/models/predict', cfg) },
  runBacktest(cfg)         { return api.post('/qlib/backtest/run', cfg) },
  getExperiments()         { return api.get('/qlib/experiments') },
  getExperiment(id)        { return api.get(`/qlib/experiments/${id}`) },
}
