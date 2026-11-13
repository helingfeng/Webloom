<script setup lang="ts">
withDefaults(defineProps<{
  size?: number
  inverse?: boolean
}>(), { size: 40, inverse: false })
</script>

<template>
  <span class="brand-identity" :class="{ inverse }" :style="{ '--brand-mark-size': `${size}px` }">
    <img src="/brand-mark.svg" alt="" :width="size" :height="size" class="brand-mark" />
    <span class="brand-copy">
      <span class="brand-name">采织</span>
      <span class="brand-english" lang="en">Webloom</span>
    </span>
  </span>
</template>

<style scoped>
.brand-identity { display: inline-flex; align-items: center; gap: 12px; vertical-align: middle; flex-shrink: 0; }
.brand-mark { display: block; flex-shrink: 0; }
.brand-copy { display: flex; flex-direction: column; gap: 3px; text-align: left; }
.brand-name { color: #173f36; font-size: calc(var(--brand-mark-size) * .5); font-weight: 700; letter-spacing: .08em; line-height: 1.15; }
.brand-english { color: #628077; font-size: clamp(10px, calc(var(--brand-mark-size) * .22), 14px); font-weight: 600; letter-spacing: .12em; line-height: 1.2; }
.inverse .brand-name { color: #f0fff8; }
.inverse .brand-english { color: #9dc8b8; }
</style>
