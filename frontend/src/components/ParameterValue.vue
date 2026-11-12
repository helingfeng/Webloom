<script setup lang="ts">
import type { VariableDefinition } from '@/types/script'
defineProps<{ modelValue?: unknown; definition: VariableDefinition; placeholder?: string }>()
const emit = defineEmits<{ 'update:modelValue': [value: unknown] }>()
const sensitive = ['secret', 'header', 'cookie', 'localStorage']
function change(value: unknown) { emit('update:modelValue', value === '' || value === null ? undefined : value) }
</script>
<template>
  <el-select v-if="definition.type === 'boolean'" :model-value="modelValue === undefined ? 'unset' : modelValue ? 'true' : 'false'" style="width:100%" @change="(v: string) => emit('update:modelValue', v === 'unset' ? undefined : v === 'true')">
    <el-option value="unset" :label="placeholder || '未指定，使用默认值'" />
    <el-option value="true" label="true（是）" />
    <el-option value="false" label="false（否）" />
  </el-select>
  <el-input-number v-else-if="definition.type === 'number'" :model-value="modelValue as number | undefined" :placeholder="placeholder || '未指定'" style="width:100%" @change="(v: number | undefined) => change(v)" />
  <el-input v-else :model-value="String(modelValue ?? '')" :type="sensitive.includes(definition.type) ? 'password' : 'text'" :show-password="sensitive.includes(definition.type)" :placeholder="placeholder || '未指定，使用默认值'" @update:model-value="change" />
</template>
