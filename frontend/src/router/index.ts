import { createRouter, createWebHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'

const router = createRouter({
  history: createWebHistory(import.meta.env.BASE_URL),
  routes: [
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
      path: '/flows',
      name: 'flows',
      component: () => import('../views/FlowsView.vue'),
    },
    {
      path: '/flows/new',
      name: 'flow-new',
      component: () => import('../views/FlowDetailView.vue'),
    },
    {
      path: '/flows/:id',
      name: 'flow-detail',
      component: () => import('../views/FlowDetailView.vue'),
    },
    {
      path: '/executions',
      name: 'executions',
      component: () => import('../views/ExecutionsView.vue'),
    },
    {
      path: '/test-cases',
      name: 'test-cases',
      component: () => import('../views/TestCasesView.vue'),
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
  ],
})

export default router
