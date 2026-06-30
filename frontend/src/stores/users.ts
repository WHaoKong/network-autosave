// 用户管理状
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiService } from '@/services'
import type { User, CreateUserRequest, UpdateUserRequest, UserQuota, NetdiskProvider } from '@/types'
import { getErrorMessage } from '@/utils/helpers'

export const useUserStore = defineStore('users', () => {
  // 状
  const users = ref<User[]>([])
  const currentUser = ref<string>('')
  const userQuota = ref<UserQuota | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  // 计算属
  const currentUserInfo = computed(() => {
    return users.value.find(user => user.is_current) || null
  })

  const validUsers = computed(() => {
    return users.value.filter(user => user.cookies_valid !== false)
  })

  const invalidUsers = computed(() => {
    return users.value.filter(user => user.cookies_valid === false)
  })

  const userStats = computed(() => {
    return {
      total: users.value.length,
      valid: validUsers.value.length,
      invalid: invalidUsers.value.length
    }
  })

  // 操作方法
  const normalizeQuota = (quota: any) => {
    if (!quota) return undefined
    const used = Number(quota.used ?? 0)
    const total = Number(quota.total ?? 0)
    const usedGb = quota.used_gb ?? (used / (1024 ** 3))
    const totalGb = quota.total_gb ?? (total / (1024 ** 3))
    return {
      used,
      total,
      used_formatted: quota.used_formatted || `${Number(usedGb).toFixed(2)} GB`,
      total_formatted: quota.total_formatted || `${Number(totalGb).toFixed(2)} GB`,
      percent: quota.percent ?? (total > 0 ? Math.round((used / total) * 100) : 0)
    }
  }

  const fetchUsers = async () => {
    loading.value = true
    error.value = null
    
    try {
      const response = await apiService.getUsers()
      if (response.success) {
        const userList = response.users || response.data?.users || []
        users.value = userList.map((user: any) => ({
          ...user,
          quota: normalizeQuota(user.quota)
        }))
        currentUser.value = response.current_user || response.data?.current_user || ''
      } else {
        throw new Error(response.message || '获取用户列表失败')
      }
    } catch (err) {
      error.value = getErrorMessage(err)
      console.error('获取用户列表失败:', err)
    } finally {
      loading.value = false
    }
  }

  const fetchUserQuota = async () => {
    try {
      const response = await apiService.getUserQuota()
      if (response.success) {
        const quota = response.quota || response.data?.quota || response.data
        // 将后端返回的数据格式化为前端需要的格式
        userQuota.value = {
          used: quota.used || 0,
          total: quota.total || 0,
          used_formatted: `${quota.used_gb || 0} GB`,
          total_formatted: `${quota.total_gb || 0} GB`,
          percent: quota.percent || 0
        }
      } else {
        throw new Error(response.message || '获取用户配额失败')
      }
    } catch (err) {
      error.value = getErrorMessage(err)
      console.error('获取用户配额失败:', err)
    }
  }

  const addUser = async (userData: CreateUserRequest) => {
    try {
      const response = await apiService.createUser(userData)
      if (response.success) {
        await fetchUsers() // 重新获取用户列表
        return true
      } else {
        throw new Error(response.message || '添加用户失败')
      }
    } catch (err) {
      error.value = getErrorMessage(err)
      throw err
    }
  }

  const updateUser = async (userData: UpdateUserRequest) => {
    try {
      const response = await apiService.updateUser(userData)
      if (response.success) {
        await fetchUsers() // 重新获取用户列表
        return true
      } else {
        throw new Error(response.message || '更新用户失败')
      }
    } catch (err) {
      error.value = getErrorMessage(err)
      throw err
    }
  }

  const deleteUser = async (username: string, provider?: NetdiskProvider) => {
    try {
      const response = await apiService.deleteUser(username, provider)
      if (response.success) {
        await fetchUsers() // 重新获取用户列表
        return true
      } else {
        throw new Error(response.message || '删除用户失败')
      }
    } catch (err) {
      error.value = getErrorMessage(err)
      throw err
    }
  }

  const switchUser = async (username: string, provider?: NetdiskProvider) => {
    try {
      const response = await apiService.switchUser(username, provider)
      if (response.success) {
        // 更新当前用户状
        users.value.forEach(user => {
          user.is_current = user.username === username && (!provider || user.provider === provider)
          // 如果返回的响应包含用户配额信息，也要格式
          if (response.current_user && response.current_user.quota && user.username === username) {
            user.quota = {
              ...response.current_user.quota,
              used_formatted: `${response.current_user.quota.used_gb || 0} GB`,
              total_formatted: `${response.current_user.quota.total_gb || 0} GB`
            }
          }
        })
        currentUser.value = username
        
        // 重新获取用户配额
        await fetchUserQuota()
        
        return true
      } else {
        throw new Error(response.message || '切换用户失败')
      }
    } catch (err) {
      error.value = getErrorMessage(err)
      throw err
    }
  }

  const getUserCookies = async (username: string, provider?: NetdiskProvider) => {
    try {
      const response = await apiService.getUserCookies(username, provider)
      if (response.success) {
        return response.cookies || response.data?.cookies
      } else {
        throw new Error(response.message || '获取用户Cookies失败')
      }
    } catch (err) {
      error.value = getErrorMessage(err)
      throw err
    }
  }

  // 辅助方法
  const findUserByUsername = (username: string) => {
    return users.value.find(user => user.username === username)
  }

  const isCurrentUser = (username: string) => {
    return currentUser.value === username
  }

  const updateUserStatus = (username: string, isValid: boolean) => {
    const user = findUserByUsername(username)
    if (user) {
      user.cookies_valid = isValid
      user.last_active = isValid ? new Date().toISOString() : user.last_active
    }
  }

  const clearError = () => {
    error.value = null
  }

  // 初始化方
  const init = async () => {
    await fetchUsers()
    await fetchUserQuota()
  }

  return {
    // 状
    users,
    currentUser,
    userQuota,
    loading,
    error,
    
    // 计算属
    currentUserInfo,
    validUsers,
    invalidUsers,
    userStats,
    
    // 操作方法
    fetchUsers,
    fetchUserQuota,
    addUser,
    updateUser,
    deleteUser,
    switchUser,
    getUserCookies,
    
    // 辅助方法
    findUserByUsername,
    isCurrentUser,
    updateUserStatus,
    clearError,
    init
  }
})
