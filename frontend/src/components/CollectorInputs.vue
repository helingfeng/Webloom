<script setup lang="ts">
import type { CollectorContract } from '@/types/collector'
defineProps<{ contract: CollectorContract; modelValue: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:modelValue': [value: Record<string, unknown>] }>()
function change(current: Record<string, unknown>, key: string, value: unknown) {
  const next = { ...current }
  if (value === '' || value === undefined || value === null) delete next[key]
  else next[key] = value
  emit('update:modelValue', next)
}
</script>
<template>
  <el-empty v-if="!Object.keys(contract.input_schema.properties).length" description="此接口无需输入参数" :image-size="60" />
  <el-form label-position="top">
    <el-form-item v-for="(field, key) in contract.input_schema.properties" :key="key" :label="String(key)" :required="contract.input_schema.required.includes(String(key))">
      <el-switch v-if="field.type === 'boolean'" :model-value="Boolean(modelValue[key])" @change="(v: unknown) => change(modelValue, String(key), v)" />
      <el-input-number v-else-if="field.type === 'number'" :model-value="modelValue[key] as number | undefined" @change="(v: unknown) => change(modelValue, String(key), v)" />
      <el-input v-else :model-value="String(modelValue[key] ?? '')" :type="field.writeOnly ? 'password' : 'text'" :show-password="field.writeOnly" :placeholder="field.default !== undefined ? `默认：${field.default}` : '请输入'" @update:model-value="(v: unknown) => change(modelValue, String(key), v)" />
      <div class="hint">{{ field.description }}</div>
    </el-form-item>
  </el-form>
</template>
<style scoped>.hint { color: #909399; font-size: 12px; width: 100%; }</style>
