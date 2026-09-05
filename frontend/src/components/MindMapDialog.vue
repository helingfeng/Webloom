<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import type { MindmapNode } from '@/types/testCase'

const props = defineProps<{
  visible: boolean
  data: MindmapNode | null
  title?: string
}>()

const emit = defineEmits<{
  (e: 'update:visible', value: boolean): void
}>()

const svgRef = ref<SVGSVGElement | null>(null)
// markmap 实例类型较复杂，此处仅需 destroy/fit 两个方法
let markmapInstance: { destroy: () => void; fit: () => void } | null = null

async function render() {
  if (!svgRef.value || !props.data) return
  const { Markmap } = await import('markmap-view')
  markmapInstance = Markmap.create(svgRef.value, { autoFit: true, duration: 300 }, props.data)
}

watch(
  () => props.visible,
  (v) => {
    if (!v) {
      markmapInstance?.destroy()
      markmapInstance = null
    }
  },
)

onBeforeUnmount(() => {
  markmapInstance?.destroy()
  markmapInstance = null
})

function handleFit() {
  markmapInstance?.fit()
}

function handleClose() {
  emit('update:visible', false)
}
</script>

<template>
  <el-dialog
    :model-value="visible"
    :title="title || '思维导图'"
    width="80%"
    top="5vh"
    destroy-on-close
    @update:model-value="handleClose"
    @opened="render"
  >
    <div class="mindmap-toolbar">
      <el-button size="small" @click="handleFit">适应画布</el-button>
    </div>
    <svg ref="svgRef" class="mindmap-svg"></svg>
  </el-dialog>
</template>

<style scoped>
.mindmap-toolbar {
  margin-bottom: 8px;
  text-align: right;
}
.mindmap-svg {
  width: 100%;
  height: 480px;
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
}
</style>
