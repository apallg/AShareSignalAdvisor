import { ref, computed } from 'vue'
import api from '../api/index.js'

const LABELS = { qmt: 'QMT 实盘', easytrader: '同花顺 实盘', fake: '' }

export function useBroker() {
  const cashEnabled = ref(true)
  const brokerType = ref('')
  const brokerLabel = computed(() => LABELS[brokerType.value] || brokerType.value)

  async function loadBroker() {
    try {
      const r = await api.get('/trading/broker')
      cashEnabled.value = r.data?.cash_enabled ?? true
      brokerType.value = r.data?.type || ''
    } catch (e) { /* 忽略 */ }
  }

  return { cashEnabled, brokerType, brokerLabel, loadBroker }
}
