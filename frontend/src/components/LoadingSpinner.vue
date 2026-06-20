<template>
  <div class="loading">{{ text }}</div>
</template>
<script setup>
defineProps({
  text: { type: String, default: '加载中...' },
})
</script>
