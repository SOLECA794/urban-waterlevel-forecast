import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  {
    path: '/',
    component: () => import('@/app/layouts/MainLayout.vue'),
    children: [
      { path: '', name: 'overview', component: () => import('@/pages/Overview.vue'), meta: { title: '系统总览' } },
      { path: 'station/:id', name: 'station-detail', component: () => import('@/pages/StationDetail.vue'), meta: { title: '监测点详情' } },
      { path: 'alerts', name: 'alert-center', component: () => import('@/pages/AlertCenter.vue'), meta: { title: '预警中心' } },
      { path: 'settings', name: 'settings', component: () => import('@/pages/Settings.vue'), meta: { title: '系统设置' } },
      { path: 'agent', name: 'agent-console', component: () => import('@/pages/AgentConsole.vue'), meta: { title: 'Agent 控制台' } },
      // 评审 P0-2：/agent 显式别名——习惯性输入 /agents 不再落空白屏
      { path: 'agents', redirect: { name: 'agent-console' } },
    ],
  },
  // 数据大屏（深色全屏，投给领导看，不带侧边栏）
  {
    path: '/dashboard',
    name: 'data-screen',
    component: () => import('@/pages/DataScreen.vue'),
    meta: { title: '数据大屏' },
  },
  // 评审 P0-2：404 兜底——不存在的路由不能静默白屏
  {
    path: '/:pathMatch(.*)*',
    name: 'not-found',
    component: () => import('@/pages/NotFound.vue'),
    meta: { title: '页面不存在' },
  },
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

router.afterEach((to) => {
  document.title = `${to.meta.title ?? ''} · 城市内涝水位预测预警系统`
})

export default router
