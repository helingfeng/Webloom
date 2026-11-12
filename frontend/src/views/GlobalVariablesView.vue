<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { useGlobalVariableStore } from '@/stores/globalVariableStore'
import { getGlobalVariable } from '@/api/globalVariables'
import { apiError } from '@/api/collectors'
import { formatDateTime } from '@/utils/format'
import type { GlobalVariable, GlobalVariableCreate } from '@/types/globalVariable'

const store = useGlobalVariableStore()
const dialog = ref(false), editingId = ref<number>(), saving = ref(false), replacing = ref(false), clearValue = ref(false), reading = ref(false)
const search = ref(''), typeFilter = ref('')
const kinds = [
  { value: 'variable', label: '脚本变量', help: '代码通过 GLOBAL_VARS["变量名"] 读取，不自动填入 INPUTS。' },
  { value: 'header', label: '请求头 Header', help: '名称为 HTTP Header 名，例如 Authorization；自动注入浏览器。' },
  { value: 'cookie', label: '登录 Cookie', help: '名称为单个 Cookie 名，值只填该 Cookie 的内容，不要粘贴整个 Cookie 请求头。' },
  { value: 'localStorage', label: '登录 localStorage', help: '名称为 localStorage 键，在目标页面脚本加载前写入，适用于登录 token。' },
]
const form = reactive<GlobalVariableCreate>({ name: '', value: '', type: 'variable', domain: '', enabled: true, description: '' })
const visible = computed(() => store.variables.filter(v => (!typeFilter.value || v.type === typeFilter.value) && `${v.name} ${v.domain} ${v.description}`.toLowerCase().includes(search.value.toLowerCase())))
const help = computed(() => kinds.find(k => k.value === form.type)?.help)
onMounted(async () => { try { await store.fetchVariables() } catch(e) { ElMessage.error(apiError(e)) } })
function open(row?: GlobalVariable) {
  editingId.value = row?.id; replacing.value = !row; clearValue.value = false
  Object.assign(form, { name: row?.name ?? '', value: '', type: row?.type ?? 'variable', domain: row?.domain ?? '', enabled: row?.enabled ?? true, description: row?.description ?? '' })
  dialog.value = true
}
async function readValue() {
  if (!editingId.value) return
  const id = editingId.value
  reading.value = true
  try { const current = (await getGlobalVariable(id)).data; if (dialog.value && editingId.value === id) { form.value = current.value; replacing.value = true; clearValue.value = false } }
  catch(e) { ElMessage.error(apiError(e)) } finally { reading.value = false }
}
async function save() {
  saving.value = true
  try {
    const { value, ...metadata } = form
    if (editingId.value) await store.updateVariable(editingId.value, { ...metadata, ...(clearValue.value ? { value: '' } : replacing.value ? { value } : {}) })
    else await store.createVariable({ ...metadata, value: value ?? '' })
    dialog.value = false; form.value = ''; ElMessage.success('已保存')
  } catch(e) { ElMessage.error(apiError(e)) } finally { saving.value = false }
}
async function toggle(row: GlobalVariable, value: unknown) {
  try { await store.updateVariable(row.id, { enabled: Boolean(value) }) }
  catch(e) { ElMessage.error(apiError(e)) }
}
async function remove(row: GlobalVariable) {
  try { await ElMessageBox.confirm(`删除「${row.name}」后，依赖此配置的脚本将不再继承该值。`, '删除全局变量', { type: 'warning' }) }
  catch { return }
  try { await store.deleteVariable(row.id); ElMessage.success('已删除') } catch(e) { ElMessage.error(apiError(e)) }
}
</script>
<template>
  <div>
    <div class="header"><div><h2>全局变量与登录态</h2><p>集中管理脚本公共配置和站点凭证，脚本可单独选择是否继承。</p></div><el-button type="primary" @click="open()">新建配置</el-button></div>
    <el-alert title="覆盖顺序：运行输入 > 更具体域名 > 父域名 > 通用配置。域名匹配忽略端口并包含子域；列表不返回明文，编辑时默认保留原值。" :closable="false" type="info" show-icon />
    <div class="filters"><el-input v-model="search" placeholder="搜索名称、域名或说明" clearable style="width:300px" /><el-select v-model="typeFilter" clearable placeholder="全部类型" style="width:180px"><el-option v-for="kind in kinds" :key="kind.value" :label="kind.label" :value="kind.value" /></el-select></div>
    <el-card><el-table v-loading="store.loading" :data="visible" empty-text="暂无匹配配置"><el-table-column prop="name" label="名称" min-width="170" /><el-table-column label="用途" width="160"><template #default="{ row }">{{ kinds.find(k => k.value === row.type)?.label }}</template></el-table-column><el-table-column label="适用域名" min-width="180"><template #default="{ row }">{{ row.domain || '通用（所有站点）' }}</template></el-table-column><el-table-column label="配置值" width="100"><template #default="{ row }">{{ row.has_value ? '••••••••' : '空值' }}</template></el-table-column><el-table-column prop="description" label="说明" min-width="180" show-overflow-tooltip /><el-table-column label="启用" width="90"><template #default="{ row }"><el-switch :model-value="row.enabled" @change="(v: unknown) => toggle(row, v)" /></template></el-table-column><el-table-column label="更新时间" width="170"><template #default="{ row }">{{ formatDateTime(row.updated_at) }}</template></el-table-column><el-table-column label="操作" width="150"><template #default="{ row }"><el-button size="small" @click="open(row)">编辑</el-button><el-button size="small" type="danger" plain @click="remove(row)">删除</el-button></template></el-table-column></el-table></el-card>
    <el-dialog v-model="dialog" :title="editingId ? '编辑配置' : '新建配置'" width="620px" @closed="form.value = ''">
      <el-form label-position="top">
        <el-form-item label="用途" required><el-select v-model="form.type" style="width:100%"><el-option v-for="kind in kinds" :key="kind.value" :label="kind.label" :value="kind.value" /></el-select><div class="hint">{{ help }}</div></el-form-item>
        <el-form-item label="名称" required><el-input v-model="form.name" maxlength="255" placeholder="例如 API_TOKEN、Authorization 或 session_id" /></el-form-item>
        <el-form-item label="适用域名"><el-input v-model="form.domain" placeholder="example.com，也可粘贴完整网页地址；留空通用" /><div class="hint">绑定域名时适用于该域及子域；更具体的配置覆盖同名通用项。</div></el-form-item>
        <el-form-item label="配置值">
          <template v-if="editingId"><el-checkbox v-model="replacing" :disabled="clearValue">替换原值</el-checkbox><el-checkbox v-model="clearValue">清空原值</el-checkbox><el-button link type="primary" :loading="reading" @click="readValue">读取当前值</el-button></template>
          <el-input v-if="!clearValue" v-model="form.value" type="password" show-password :disabled="!replacing" :placeholder="editingId && !replacing ? '保持原值，无需重新填写' : '填写配置内容'" />
          <div class="hint">无需在修改域名、备注或启停时重新填写凭证。</div>
        </el-form-item>
        <el-form-item label="说明"><el-input v-model="form.description" type="textarea" /></el-form-item>
        <el-form-item label="启用"><el-switch v-model="form.enabled" /></el-form-item>
      </el-form>
      <template #footer><el-button @click="dialog = false">取消</el-button><el-button type="primary" :loading="saving" @click="save">保存</el-button></template>
    </el-dialog>
  </div>
</template>
<style scoped>.header { display:flex; justify-content:space-between; align-items:center; margin-bottom:20px } h2 { margin:0 0 8px } p,.hint { color:#909399;font-size:13px } .hint { width:100%;line-height:1.8 } .filters { display:flex;gap:12px;margin:16px 0 }</style>
