<script setup lang="ts">
import { onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { useWorkspaceStore } from '@/stores/workspaceStore'
import BrandIdentity from '@/components/BrandIdentity.vue'

const route = useRoute()
const wsStore = useWorkspaceStore()

onMounted(() => {
  wsStore.fetchWorkspaces()
})

interface MenuLeaf {
  path: string
  label: string
  icon: string
}

interface MenuNode extends MenuLeaf {
  children?: MenuLeaf[]
}

const menuItems: MenuNode[] = [
  { path: '/', label: '首页', icon: 'HomeFilled' },
  { path: '/scripts', label: '脚本管理', icon: 'Document' },
  { path: '/executions', label: '执行记录', icon: 'List' },
  { path: '/workspaces', label: '项目空间', icon: 'Folder' },
  { path: '/global-variables', label: '全局变量', icon: 'Key' },
  { path: '/datasources', label: '数据源', icon: 'Coin' },
  { path: '/data-views', label: '数据视图', icon: 'DataAnalysis' },
  { path: '/mcp', label: 'MCP 服务', icon: 'Connection' },
  {
    path: '/open-platform',
    label: '开放平台',
    icon: 'Platform',
    children: [
      { path: '/collectors', label: '采集接口', icon: 'Connection' },
      { path: '/collector-tasks', label: '采集任务与数据', icon: 'DataAnalysis' },
      { path: '/open-apps', label: '开放应用', icon: 'Avatar' },
      { path: '/open-logs', label: '调用日志', icon: 'Tickets' },
      { path: '/open-docs', label: '接入文档', icon: 'Reading' },
    ],
  },
]

function isActive(path: string) {
  if (path === '/') {
    return route.path === '/'
  }
  return route.path.startsWith(path)
}
</script>

<template>
  <el-container class="layout-container">
    <el-aside width="200px" class="sidebar">
      <router-link to="/" class="logo" aria-label="采织 Webloom 首页">
        <BrandIdentity inverse />
      </router-link>
      <div class="workspace-switch">
        <el-select
          :model-value="wsStore.currentWorkspaceId"
          placeholder="选择项目空间"
          size="default"
          class="workspace-select"
          @change="wsStore.setCurrentWorkspace"
        >
          <el-option
            v-for="ws in wsStore.workspaces"
            :key="ws.id"
            :label="ws.name"
            :value="ws.id"
          />
        </el-select>
      </div>
      <el-menu
        :default-active="route.path"
        class="menu"
        router
        background-color="#173a32"
        text-color="#b4cec4"
        active-text-color="#82e2bb"
      >
        <template v-for="item in menuItems" :key="item.path">
          <el-sub-menu v-if="item.children" :index="item.path">
            <template #title>
              <el-icon>
                <component :is="item.icon" />
              </el-icon>
              <span>{{ item.label }}</span>
            </template>
            <el-menu-item
              v-for="child in item.children"
              :key="child.path"
              :index="child.path"
              :class="{ active: isActive(child.path) }"
            >
              <el-icon>
                <component :is="child.icon" />
              </el-icon>
              <span>{{ child.label }}</span>
            </el-menu-item>
          </el-sub-menu>
          <el-menu-item v-else :index="item.path" :class="{ active: isActive(item.path) }">
            <el-icon>
              <component :is="item.icon" />
            </el-icon>
            <span>{{ item.label }}</span>
          </el-menu-item>
        </template>
      </el-menu>
    </el-aside>
    <el-container>
      <el-main class="main-content">
        <slot />
      </el-main>
    </el-container>
  </el-container>
</template>

<style scoped>
.layout-container {
  height: 100vh;
  width: 100%;
}

.sidebar {
  background-color: #173a32;
  color: #fff;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.menu {
  border-right: none;
  flex: 1;
  overflow-y: auto;
}

.logo {
  min-height: 84px;
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding: 0 20px;
  text-decoration: none;
  border-bottom: 1px solid #2a5144;
}

.logo:hover { background: #20493e; }
.logo:focus-visible { outline: 2px solid #82e2bb; outline-offset: -3px; }

.workspace-switch {
  padding: 12px 14px;
  border-bottom: 1px solid #2a5144;
}

.workspace-select {
  width: 100%;
}

.main-content {
  flex: 1;
  min-width: 0;
  background-color: #f6f9f8;
  padding: 20px;
  overflow-y: auto;
}

:deep(.el-menu-item.active) {
  color: #82e2bb !important;
}
</style>
