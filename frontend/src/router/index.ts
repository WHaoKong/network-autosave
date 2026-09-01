import { createRouter, createWebHistory } from 'vue-router'
import { useAuthStore } from '@/stores/auth'
import { PAGE_TITLES } from '@/utils/constants'

const LoginView = () => import('@/views/login/LoginView.vue')
const DashboardView = () => import('@/views/dashboard/DashboardView.vue')
const TasksView = () => import('@/views/tasks/TasksView.vue')
const UsersView = () => import('@/views/users/UsersView.vue')
const SettingsView = () => import('@/views/settings/SettingsView.vue')

const routes = [
  {
    path: '/',
    redirect: '/dashboard'
  },
  {
    path: '/login',
    name: 'Login',
    component: LoginView,
    meta: {
      title: PAGE_TITLES.LOGIN,
      requiresAuth: false,
      hideInMenu: true
    }
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: DashboardView,
    meta: {
      title: PAGE_TITLES.DASHBOARD,
      requiresAuth: true,
      icon: 'Dashboard'
    }
  },
  {
    path: '/tasks',
    name: 'Tasks',
    component: TasksView,
    meta: {
      title: PAGE_TITLES.TASKS,
      requiresAuth: true,
      icon: 'List'
    }
  },
  {
    path: '/users',
    name: 'Users',
    component: UsersView,
    meta: {
      title: PAGE_TITLES.USERS,
      requiresAuth: true,
      icon: 'User'
    }
  },
  {
    path: '/settings',
    name: 'Settings',
    component: SettingsView,
    meta: {
      title: PAGE_TITLES.SETTINGS,
      requiresAuth: true,
      icon: 'Setting'
    }
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/dashboard'
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes
})

router.beforeEach(async (to, _from, next) => {
  const authStore = useAuthStore()

  if (to.meta.title) {
    document.title = `${to.meta.title} - \u7f51\u76d8\u81ea\u52a8\u8f6c\u5b58`
  }

  if (to.meta.requiresAuth && !authStore.isLoggedIn) {
    await authStore.initAuth()

    if (!authStore.isLoggedIn) {
      next({
        path: '/login',
        query: { redirect: to.fullPath }
      })
      return
    }
  }

  if (to.path === '/login' && authStore.isLoggedIn) {
    next('/')
    return
  }

  next()
})

router.afterEach((to) => {
  console.log(`\u5bfc\u822a\u5230: ${to.path}`)
})

export default router

export const getMenuRoutes = () => {
  return routes.filter(route =>
    route.meta?.requiresAuth &&
    !route.meta?.hideInMenu &&
    route.name !== 'Dashboard'
  )
}

export const getBreadcrumbs = (currentRoute: any) => {
  const breadcrumbs = [
    {
      title: '\u9996\u9875',
      path: '/dashboard'
    }
  ]

  if (currentRoute.meta?.title && currentRoute.path !== '/dashboard') {
    breadcrumbs.push({
      title: currentRoute.meta.title,
      path: currentRoute.path
    })
  }

  return breadcrumbs
}
