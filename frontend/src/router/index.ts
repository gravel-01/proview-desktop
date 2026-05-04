import { createRouter, createWebHashHistory } from 'vue-router'
import { useInterviewStore } from '../stores/interview'
import { useAuthStore } from '../stores/auth'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/login', redirect: '/config' },
    { path: '/register', redirect: '/config' },
    { path: '/config', name: 'runtime-config', component: () => import('../views/RuntimeConfigView.vue'), meta: { public: true } },
    { path: '/', name: 'setup', component: () => import('../views/SetupView.vue') },
    {
      path: '/interview',
      name: 'interview',
      component: () => import('../views/InterviewView.vue')
    },
    {
      path: '/report',
      name: 'report',
      component: () => import('../views/ReportView.vue')
    },
    {
      path: '/report/:sessionId',
      name: 'report-history',
      component: () => import('../views/ReportView.vue')
    },
    {
      path: '/summary',
      name: 'summary',
      component: () => import('../views/SummaryView.vue')
    },
    {
      path: '/resume-optimizer',
      name: 'resume-optimizer',
      component: () => import('../views/ResumeOptimizerView.vue')
    },
    {
      path: '/resume-builder',
      name: 'resume-builder',
      component: () => import('../views/ResumeBuilderView.vue')
    },
    {
      path: '/resume-entry',
      component: () => import('../views/ResumeBuilderEntryView.vue')
    },
    {
      path: '/history',
      name: 'history',
      component: () => import('../views/HistoryListView.vue')
    },
    {
      path: '/history/:sessionId',
      name: 'history-detail',
      component: () => import('../views/HistoryDetailView.vue')
    },
    {
      path: '/my-resumes',
      name: 'my-resumes',
      component: () => import('../views/MyResumesView.vue')
    },
    {
      path: '/monitoring',
      name: 'monitoring',
      component: () => import('../views/MonitoringView.vue')
    },
    {
      path: '/career-planning',
      name: 'career-planning',
      component: () => import('../views/CareerPlanningView.vue'),
      redirect: '/career-planning/overview',
      children: [
        {
          path: 'overview',
          name: 'career-planning-overview',
          component: () => import('../views/career-planning/CareerPlanningOverviewPage.vue')
        },
        {
          path: 'roadmap',
          name: 'career-planning-roadmap',
          component: () => import('../views/career-planning/CareerPlanningRoadmapPage.vue')
        },
        {
          path: 'tasks',
          name: 'career-planning-tasks',
          component: () => import('../views/career-planning/CareerPlanningTasksPage.vue')
        },
        {
          path: 'docs',
          name: 'career-planning-docs',
          component: () => import('../views/career-planning/CareerPlanningDocsPage.vue')
        }
      ]
    }
  ]
})

let authInitialized = false

router.beforeEach(async (to) => {
  const auth = useAuthStore()
  const store = useInterviewStore()

  // 单机版启动时拉取当前本机用户信息，供界面展示。
  if (!authInitialized) {
    authInitialized = true
    await auth.tryRestore()
  }

  if (to.name === 'interview') {
    if (store.shouldRedirectInterviewToReport) return '/report'
    if (!store.canEnterInterviewRoom) return '/'
  }
})

export default router
