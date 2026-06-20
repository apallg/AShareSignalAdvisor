import { ref } from 'vue'
import api from '../api/index.js'

export function useBroker() {
  const cashEnabled = ref(true)

  async function loadBroker() {
    try {
      const r = await api.get('/trading/broker')
      cashEnabled.value = r.data?.cash_enabled ?? true
    } catch (e) { /* 忽略 */ }
  }

  return { cashEnabled, loadBroker }
}
