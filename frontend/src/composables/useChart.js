import { ref, onUnmounted, nextTick } from 'vue'

export function useChart(initOptions) {
  const chartRef = ref(null)
  let instance = null

  async function render(getOptions) {
    await nextTick()
    const el = chartRef.value
    if (!el) return
    if (instance) { instance.dispose(); instance = null }

    const echarts = await import('echarts')
    instance = echarts.init(el)
    const opts = getOptions()
    if (opts) instance.setOption(opts)
    window.addEventListener('resize', onResize)
  }

  function onResize() {
    if (instance) instance.resize()
  }

  function dispose() {
    if (instance) { instance.dispose(); instance = null }
    window.removeEventListener('resize', onResize)
  }

  onUnmounted(dispose)

  return { chartRef, render, dispose }
}
