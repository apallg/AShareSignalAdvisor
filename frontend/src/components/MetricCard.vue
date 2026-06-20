<template>
  <div class="card metric">
    <div class="value" :class="colorClass">{{ displayValue }}</div>
    <div class="label"><slot name="label">{{ label }}</slot></div>
    <div v-if="delta != null" :class="['delta', delta > 0 ? 'up' : delta < 0 ? 'down' : '']">
      {{ delta > 0 ? '+' : '' }}{{ delta.toFixed(2) }}%
    </div>
  </div>
</template>
<script setup>
import { computed } from 'vue'
const props = defineProps({
  value: { default: '--' },
  label: { type: String, default: '' },
  delta: { default: null },
  color: { type: String, default: '' }, // 'up' | 'down' | ''
})
const displayValue = computed(() => {
  if (props.value == null) return '--'
  return props.value
})
const colorClass = computed(() => {
  if (props.color === 'up') return 'text-red'
  if (props.color === 'down') return 'text-green'
  return ''
})
</script>
