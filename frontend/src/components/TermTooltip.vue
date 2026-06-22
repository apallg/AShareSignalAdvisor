<template>
  <span class="term-tooltip" @mouseenter="show=true" @mouseleave="show=false">
    <slot />
    <sup class="tip-badge">?</sup>
    <transition name="fade">
      <div v-if="show" class="tip-card">
        <div class="tip-title">{{ term.english }}</div>
        <div class="tip-desc">{{ term.desc }}</div>
        <div v-if="term.formula" class="tip-formula">{{ term.formula }}</div>
      </div>
    </transition>
  </span>
</template>
<script setup>
import { ref, computed } from "vue"
import { getTerm } from "../utils/terms.js"
const props = defineProps({ name: String })
const show = ref(false)
const term = computed(() => getTerm(props.name))
</script>
<style scoped>
.term-tooltip { position:relative; cursor:help; display:inline-flex; align-items:center; gap:2px; }
.tip-badge { font-size:10px; color:#999; opacity:0.6; font-weight:bold; }
.tip-card { position:absolute; bottom:calc(100% + 8px); left:50%; transform:translateX(-50%); z-index:1000; width:280px; padding:12px 16px; background:#1a1a2e; color:#e0e0e0; border-radius:8px; font-size:12px; line-height:1.6; box-shadow:0 4px 16px rgba(0,0,0,0.2); }
.tip-title { font-weight:600; color:#e94560; margin-bottom:4px; }
.tip-formula { margin-top:6px; padding-top:6px; border-top:1px solid #2a2a4e; font-family:monospace; font-size:11px; color:#888; }
.fade-enter-active, .fade-leave-active { transition:opacity 0.15s; }
.fade-enter-from, .fade-leave-to { opacity:0; }
</style>
