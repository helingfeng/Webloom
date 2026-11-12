<script setup lang="ts">
import type { CollectorContract } from '@/types/collector'
import type { VariableDefinition } from '@/types/script'
import ParameterValue from './ParameterValue.vue'
defineProps<{ contract: CollectorContract; modelValue: Record<string, unknown> }>()
const emit = defineEmits<{ 'update:modelValue': [value: Record<string, unknown>] }>()
function definition(name: string, field: { type: string; writeOnly?: boolean }): VariableDefinition {
  return { name, type: field.writeOnly ? 'secret' : field.type as VariableDefinition['type'] }
}
function change(current: Record<string, unknown>, key: string, value: unknown) {
  const next = { ...current }
  if (value === undefined) delete next[key]
  else next[key] = value
  emit('update:modelValue', next)
}
</script>
<template>
  <el-empty v-if="!Object.keys(contract.input_schema.properties).length" description="此接口无需输入参数" :image-size="60" />
  <el-form label-position="top">
    <el-form-item v-for="(field, key) in contract.input_schema.properties" :key="key" :label="String(key)" :required="contract.input_schema.required.includes(String(key))">
      <ParameterValue :definition="definition(String(key), field)" :model-value="modelValue[key]" :placeholder="field.default !== undefined ? `默认：${field.default}` : '未指定'" @update:model-value="(v: unknown) => change(modelValue, String(key), v)" />
      <div class="hint">{{ field.description }}</div>
    </el-form-item>
  </el-form>
</template>
<style scoped>.hint { color: #909399; font-size: 12px; width: 100%; }</style>
