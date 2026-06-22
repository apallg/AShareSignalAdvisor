import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', redirect: '/market' },
  { path: '/market', name: 'market', component: () => import('../views/MarketView.vue') },
  { path: '/stock', name: 'stock', component: () => import('../views/StockView.vue') },
  { path: '/sectors', name: 'sectors', component: () => import('../views/SectorView.vue') },
  { path: '/portfolio', name: 'portfolio', component: () => import('../views/PortfolioView.vue') },
  { path: '/alerts', name: 'alerts', component: () => import('../views/AlertView.vue') },
  { path: '/backtest', name: 'backtest', component: () => import('../views/BacktestView.vue') },
  { path: '/lab', name: 'lab', component: () => import('../views/StrategyLab.vue') },
  { path: '/sentiment', name: 'sentiment', component: () => import('../views/SentimentView.vue') },
  { path: '/trading', name: 'trading', component: () => import('../views/TradingView.vue') },
  { path: '/live', name: 'live', component: () => import('../views/LiveTradingView.vue') },
  { path: '/editor', name: 'editor', component: () => import('../views/StrategyEditor.vue') },
  { path: '/qlib', name: 'qlib', component: () => import('../views/QlibLab.vue') },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router
