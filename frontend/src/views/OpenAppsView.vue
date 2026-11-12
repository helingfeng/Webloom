<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { formatDateTime } from '@/utils/format'
import {
  createOpenApp,
  deleteOpenApp,
  getOpenApp,
  listOpenApps,
  regenerateOpenAppSecret,
  updateOpenApp,
} from '@/api/openPlatform'
import type { OpenApp, OpenAppCreate } from '@/types/openPlatform'

const loading = ref(false)
const apps = ref<OpenApp[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = 20

const dialogVisible = ref(false)
const editingId = ref<number | null>(null)
const form = reactive<OpenAppCreate>({
  name: '',
  description: '',
  enabled: true,
})

// 凭证弹窗：创建成功 / 查看详情 / 重新生成后展示完整密钥
const credentialVisible = ref(false)
const credential = reactive({ name: '', app_key: '', app_secret: '' })
const secretVisible = ref(false)

async function fetchApps() {
  loading.value = true
  try {
    const res = await listOpenApps((page.value - 1) * pageSize, pageSize)
    apps.value = res.data.items
    total.value = res.data.total
  } catch (error) {
    ElMessage.error('加载开放应用失败')
    console.error(error)
  } finally {
    loading.value = false
  }
}

onMounted(fetchApps)

function openCreate() {
  editingId.value = null
  form.name = ''
  form.description = ''
  form.enabled = true
  dialogVisible.value = true
}

function openEdit(row: OpenApp) {
  editingId.value = row.id
  form.name = row.name
  form.description = row.description
  form.enabled = row.enabled
  dialogVisible.value = true
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入应用名称')
    return
  }
  try {
    if (editingId.value) {
      await updateOpenApp(editingId.value, { ...form })
      ElMessage.success('更新成功')
      dialogVisible.value = false
      await fetchApps()
    } else {
      const res = await createOpenApp({ ...form })
      dialogVisible.value = false
      credential.name = res.data.name
      credential.app_key = res.data.app_key
      credential.app_secret = res.data.app_secret
      credentialVisible.value = true
      await fetchApps()
    }
  } catch (error) {
    ElMessage.error('保存失败')
    console.error(error)
  }
}

async function handleToggle(row: OpenApp) {
  try {
    await updateOpenApp(row.id, { enabled: row.enabled })
    ElMessage.success(row.enabled ? '已启用' : '已停用')
  } catch (error) {
    row.enabled = !row.enabled
    ElMessage.error('操作失败')
    console.error(error)
  }
}

async function showCredential(row: OpenApp) {
  // 详情需要单独拉取（列表不回传 secret）
  try {
    const res = await getOpenApp(row.id)
    credential.name = res.data.name
    credential.app_key = res.data.app_key
    credential.app_secret = res.data.app_secret
    secretVisible.value = false
    credentialVisible.value = true
  } catch (error) {
    ElMessage.error('加载凭证失败')
    console.error(error)
  }
}

async function handleRegenerate(row: OpenApp) {
  try {
    await ElMessageBox.confirm(
      '重新生成后旧 App Secret 立即失效，调用方需更新密钥。确定继续吗？',
      '重新生成密钥',
      { confirmButtonText: '重新生成', cancelButtonText: '取消', type: 'warning' }
    )
    const res = await regenerateOpenAppSecret(row.id)
    credential.name = row.name
    credential.app_key = res.data.app_key
    credential.app_secret = res.data.app_secret
    secretVisible.value = false
    credentialVisible.value = true
    await fetchApps()
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error('重新生成失败')
      console.error(error)
    }
  }
}

async function handleDelete(id: number) {
  try {
    await ElMessageBox.confirm('删除后该应用将无法调用开放接口，确定删除吗？', '提示', {
      confirmButtonText: '确定',
      cancelButtonText: '取消',
      type: 'warning',
    })
    await deleteOpenApp(id)
    ElMessage.success('删除成功')
    await fetchApps()
  } catch (error) {
    if (error !== 'cancel') {
      console.error(error)
    }
  }
}

async function copyText(text: string) {
  try {
    await navigator.clipboard.writeText(text)
    ElMessage.success('已复制到剪贴板')
  } catch {
    ElMessage.error('复制失败，请手动选择复制')
  }
}

function handlePageChange() {
  fetchApps()
}
</script>

<template>
  <div>
    <div class="page-header">
      <h2>开放应用</h2>
      <el-button type="primary" @click="openCreate">
        <el-icon><Plus /></el-icon> 新建应用
      </el-button>
    </div>

    <el-alert
      type="info"
      :closable="false"
      show-icon
      style="margin-bottom: 20px"
      title="创建应用后，在「采集接口」授权该应用。调用方使用 Authorization: Bearer AppKey.AppSecret 发起采集并查询结果；完整调用凭证可在应用详情复制。"
    />

    <el-card v-loading="loading">
      <el-table :data="apps" style="width: 100%">
        <el-table-column prop="id" label="ID" width="70" />
        <el-table-column prop="name" label="应用名称" min-width="140" show-overflow-tooltip />
        <el-table-column label="App Key" min-width="180" show-overflow-tooltip>
          <template #default="{ row }">
            <code class="mono">{{ row.app_key }}</code>
            <el-button link type="primary" size="small" @click="copyText(row.app_key)">复制</el-button>
          </template>
        </el-table-column>
        <el-table-column label="App Secret" min-width="120">
          <template #default>
            <span class="masked">••••••••</span>
          </template>
        </el-table-column>
        <el-table-column label="状态" width="90">
          <template #default="{ row }">
            <el-switch v-model="row.enabled" @change="handleToggle(row)" />
          </template>
        </el-table-column>
        <el-table-column prop="description" label="描述" min-width="150" show-overflow-tooltip />
        <el-table-column label="创建时间" min-width="160">
          <template #default="{ row }">
            {{ formatDateTime(row.created_at) }}
          </template>
        </el-table-column>
        <el-table-column label="操作" width="230" fixed="right">
          <template #default="{ row }">
            <el-button size="small" type="primary" plain @click="showCredential(row)">凭证</el-button>
            <el-button size="small" @click="openEdit(row)">编辑</el-button>
            <el-button size="small" type="danger" @click="handleDelete(row.id)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
      <div class="pagination-wrap">
        <el-pagination
          v-model:current-page="page"
          layout="total, prev, pager, next"
          :total="total"
          :page-size="pageSize"
          @current-change="handlePageChange"
        />
      </div>
    </el-card>

    <!-- 新建/编辑 -->
    <el-dialog
      v-model="dialogVisible"
      :title="editingId ? '编辑开放应用' : '新建开放应用'"
      width="500px"
    >
      <el-form :model="form" label-width="90px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="例如：数据中台" />
        </el-form-item>
        <el-form-item label="启用">
          <el-switch v-model="form.enabled" />
        </el-form-item>
        <el-form-item label="描述">
          <el-input v-model="form.description" type="textarea" :rows="2" placeholder="用途说明" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="dialogVisible = false">取消</el-button>
        <el-button type="primary" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>

    <!-- 凭证展示 -->
    <el-dialog v-model="credentialVisible" :title="`应用凭证：${credential.name}`" width="560px">
      <el-alert
        type="warning"
        :closable="false"
        show-icon
        title="App Secret 仅在创建/查看/重新生成时可见，请妥善保存；泄露后请立即重新生成。"
        style="margin-bottom: 16px"
      />
      <el-form label-width="90px">
        <el-form-item label="App Key">
          <div class="cred-row">
            <code class="mono">{{ credential.app_key }}</code>
            <el-button size="small" @click="copyText(credential.app_key)">复制</el-button>
          </div>
        </el-form-item>
        <el-form-item label="App Secret">
          <div class="cred-row">
            <code class="mono">{{ secretVisible ? credential.app_secret : '••••••••••••••••••••••••' }}</code>
            <el-button size="small" @click="secretVisible = !secretVisible">
              {{ secretVisible ? '隐藏' : '显示' }}
            </el-button>
            <el-button size="small" @click="copyText(credential.app_secret)">复制</el-button>
          </div>
        </el-form-item>
      </el-form>
      <p style="color:#909399;font-size:13px">完整调用凭证格式为 App Key.App Secret，可粘贴到调用体验页，或在请求头中使用 Authorization: Bearer。</p>
      <template #footer>
        <el-button type="primary" @click="copyText(`${credential.app_key}.${credential.app_secret}`)">复制完整调用凭证</el-button>
        <el-button @click="credentialVisible = false">关闭</el-button>
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

.mono {
  font-family: 'SFMono-Regular', Consolas, 'Liberation Mono', monospace;
  font-size: 13px;
}

.masked {
  color: #909399;
  letter-spacing: 2px;
}

.pagination-wrap {
  margin-top: 16px;
  display: flex;
  justify-content: flex-end;
}

.cred-row {
  display: flex;
  align-items: center;
  gap: 8px;
  width: 100%;
}
</style>
