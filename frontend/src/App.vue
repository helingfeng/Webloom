<script setup lang="ts">
import { RouterView, useRoute } from 'vue-router'
const route = useRoute()
import AppLayout from './components/AppLayout.vue'
</script>

<template>
  <RouterView v-if="route.meta.publicPortal" />
  <AppLayout v-else>
    <RouterView />
  </AppLayout>
</template>

<style>
html, body, #app {
  margin: 0;
  padding: 0;
  height: 100%;
}
</style>
