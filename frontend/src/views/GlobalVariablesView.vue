<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useGlobalVariableStore } from '@/stores/globalVariableStore'
import { formatDateTime } from '@/utils/format'
import { ElMessage, ElMessageBox } from 'element-plus'
import type { GlobalVariableCreate } from '@/types/globalVariable'

const gvStore = useGlobalVariableStore()

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)

const form = reactive<GlobalVariableCreate>({
  name: '',
  value: '',
  type: 'header',
  domain: '',
  enabled: true,
  description: '',
})

onMounted(() => {
  gvStore.fetchVariables()
})

function openCreate() {
  editingId.value = null
  form.name = ''
  form.value = ''
  form.type = 'header'
  form.domain = ''
  form.enabled = true
  form.description = ''
  dialogVisible.value = true
}

function openEdit(row: any) {
  editingId.value = row.id
  form.name = row.name
  form.value = row.value
  form.type = row.type
  form.domain = row.domain || ''
  form.enabled = row.enabled
  form.description = row.description
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入变量名')
    return
  }
  try {
    if (editingId.value) {
      await gvStore.updateVariable(editingId.value, { ...form })
      ElMessage.success('更新成功')
    } else {
      await gvStore.createVariable({ ...form })
      ElMessage.success('创建成功')
    }
    dialogVisible.value = false
  } catch (error) {
    ElMessage.error('保存失败')
    console.error(error)
  }
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('确定删除该全局变量吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await gvStore.deleteVariable(id)
    ElMessage.success('删除成功')
  } catch (error) {
    if (error !== 'cancel') {
      console.error(error)
    }
  }
}
</script>

<template>
  <div>
    <div class="page-header">
      <h2>全局变量</h2>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> 新建变量
      </el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 20px"
      title="header 类型注入浏览器请求头；cookie 类型注入登录 Cookie；localStorage 类型在访问脚本起始 URL 前自动写入（适合 token 存 localStorage 的系统）；variable 类型注入脚本中的 GLOBAL_VARS 字典。绑定域名后，仅当脚本起始 URL 的域名与之匹配时才加载；留空则对所有域名生效。"
    />

    <el-card v-loading="gvStore.loading">
      <el-table :data="gvStore.variables" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="名称" min-width="150" show-overflow-tooltip />
        <el-table-column prop="value" label="值" min-width="200" show-overflow-tooltip>
          <template #default="{ row }">
            <span>{{ row.value }}</span>
          </template>
        </el-table-column>
        <el-table-column label="类型" width="120">
          <template #default="{ row }">
            <el-tag :type="row.type === 'header' ? 'warning' : row.type === 'localStorage' ? 'success' : row.type === 'cookie' ? 'danger' : 'primary'">
              {{ row.type === 'header' ? '公共 Header' : row.type === 'localStorage' ? 'LocalStorage' : row.type === 'cookie' ? 'Cookie' : '变量' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="绑定域名" min-width="150" show-overflow-tooltip>
          <template #default="{ row }">
            <el-tag v-if="row.domain" type="warning" size="small">{{ row.domain }}</el-tag>
            <el-tag v-else type="info" size="small">所有域名</el-tag>
          </template>
        </el-table-column>
        <el-table-column label="启用" width="80">
          <template #default="{ row }">
            <el-tag :type="row.enabled ? 'success' : 'info'">
              {{ row.enabled ? '启用' : '禁用' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="更新时间" min-width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.updated_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="150" fixed="right">
          <template #default="{ row }">
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑全局变量' : '新建全局变量'"
      width="500px"
    >
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称" required>
          <el-input
            v-model="form.name"
            :placeholder="form.type === 'localStorage' ? '例如：token / refreshToken' : form.type === 'cookie' ? '例如：SESSIONID / token（cookie 名）' : '例如：Authorization / X-Tenant-Id'"
          />
        </el-form-item>
        <el-form-item label="值">
          <el-input
            v-model="form.value"
            :type="form.type === 'variable' ? 'password' : 'textarea'"
            :rows="form.type === 'variable' ? 1 : 3"
            :placeholder="form.type === 'localStorage' ? '该 localStorage 键对应的值（如 token 内容）' : form.type === 'cookie' ? '该 cookie 对应的值（如 SESSIONID 内容）' : '变量值'"
          />
        </el-form-item>
        <el-form-item label="类型">
          <el-radio-group v-model="form.type">
            <el-radio value="header">公共 Header</el-radio>
            <el-radio value="cookie">Cookie</el-radio>
            <el-radio value="localStorage">LocalStorage</el-radio>
            <el-radio value="variable">变量</el-radio>
          </el-radio-group>
        </el-form-item>
        <el-form-item label="绑定域名">
          <el-input
            v-model="form.domain"
            placeholder="可选，例如：admin.example.com 或 example.com（含子域名）；留空对所有域名生效"
          />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="描述" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
}
</style>
