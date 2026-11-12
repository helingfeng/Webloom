import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
    { path: '/collectors', component: () => import('../views/CollectorsView.vue') },
    { path: '/collector-tasks', component: () => import('../views/CollectorTasksView.vue') },
    { path: '/collection-portal', meta: { publicPortal: true }, component: () => import('../views/CollectionPortalView.vue') },
    {
      path: '/',
      name: 'home',
      component: HomeView,
    },
    {
      path: '/scripts',
      name: 'scripts',
      component: () => import('../views/ScriptsView.vue'),
    },
    {
      path: '/scripts/new',
      name: 'script-new',
      component: () => import('../views/ScriptDetailView.vue'),
    },
    {
      path: '/scripts/:id',
      name: 'script-detail',
      component: () => import('../views/ScriptDetailView.vue'),
    },
    {
      path: '/executions',
      name: 'executions',
      component: () => import('../views/ExecutionsView.vue'),
    },
    {
      path: '/workspaces',
      name: 'workspaces',
      component: () => import('../views/WorkspacesView.vue'),
    },
    {
      path: '/global-variables',
      name: 'global-variables',
      component: () => import('../views/GlobalVariablesView.vue'),
    },
    {
      path: '/datasources',
      name: 'datasources',
      component: () => import('../views/DatasourcesView.vue'),
    },
    {
      path: '/datasources/:id/workbench',
      name: 'datasource-workbench',
      component: () => import('../views/DatasourceWorkbenchView.vue'),
    },
    {
      path: '/data-views',
      name: 'data-views',
      component: () => import('../views/DataViewsView.vue'),
    },
    {
      path: '/mcp',
      name: 'mcp',
      component: () => import('../views/McpView.vue'),
    },
    {
      path: '/open-apps',
      name: 'open-apps',
      component: () => import('../views/OpenAppsView.vue'),
    },
    {
      path: '/open-logs',
      name: 'open-logs',
      component: () => import('../views/OpenLogsView.vue'),
    },
    {
      path: '/open-docs',
      name: 'open-docs',
      component: () => import('../views/OpenDocsView.vue'),
    },
  ],
})

export default router
