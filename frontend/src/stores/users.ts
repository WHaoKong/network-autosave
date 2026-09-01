import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { apiService } from '@/services'
import type {
  User,
  CreateUserRequest,
  UpdateUserRequest,
  UserQuota,
  NetdiskProvider,
  QuarkSigninConfigRequest,
  QuarkSigninResult
} from '@/types'
import { getErrorMessage } from '@/utils/helpers'

export const useUserStore = defineStore('users', () => {
  const users = ref<User[]>([])
  const currentUser = ref<string>('')
  const userQuota = ref<UserQuota | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const currentUserInfo = computed(() => {
    return users.value.find(user => user.is_current) || null
  })

  const validUsers = computed(() => {
    return users.value.filter(user => user.cookies_valid !== false)
  })

  const invalidUsers = computed(() => {
    return users.value.filter(user => user.cookies_valid === false)
  })

  const userStats = computed(() => ({
    total: users.value.length,
    valid: validUsers.value.length,
    invalid: invalidUsers.value.length
  }))

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
        throw new Error(response.message || '\u83b7\u53d6\u7528\u6237\u5217\u8868\u5931\u8d25')
      }
    } catch (err) {
      error.value = getErrorMessage(err)
      console.error('\u83b7\u53d6\u7528\u6237\u5217\u8868\u5931\u8d25:', err)
    } finally {
      loading.value = false
    }
  }

  const fetchUserQuota = async () => {
    try {
      const response = await apiService.getUserQuota()
      if (response.success) {
        const quota = response.quota || response.data?.quota || response.data
        userQuota.value = {
          used: quota.used || 0,
          total: quota.total || 0,
          used_formatted: `${quota.used_gb || 0} GB`,
          total_formatted: `${quota.total_gb || 0} GB`,
          percent: quota.percent || 0
        }
      } else {
        throw new Error(response.message || '\u83b7\u53d6\u7528\u6237\u914d\u989d\u5931\u8d25')
      }
    } catch (err) {
      error.value = getErrorMessage(err)
      console.error('\u83b7\u53d6\u7528\u6237\u914d\u989d\u5931\u8d25:', err)
    }
  }

  const addUser = async (userData: CreateUserRequest) => {
    try {
      const response = await apiService.createUser(userData)
      if (response.success) {
        await fetchUsers()
        return true
      }
      throw new Error(response.message || '\u6dfb\u52a0\u7528\u6237\u5931\u8d25')
    } catch (err) {
      error.value = getErrorMessage(err)
      throw err
    }
  }

  const updateUser = async (userData: UpdateUserRequest) => {
    try {
      const response = await apiService.updateUser(userData)
      if (response.success) {
        await fetchUsers()
        return true
      }
      throw new Error(response.message || '\u66f4\u65b0\u7528\u6237\u5931\u8d25')
    } catch (err) {
      error.value = getErrorMessage(err)
      throw err
    }
  }

  const deleteUser = async (username: string, provider?: NetdiskProvider) => {
    try {
      const response = await apiService.deleteUser(username, provider)
      if (response.success) {
        await fetchUsers()
        return true
      }
      throw new Error(response.message || '\u5220\u9664\u7528\u6237\u5931\u8d25')
    } catch (err) {
      error.value = getErrorMessage(err)
      throw err
    }
  }

  const switchUser = async (username: string, provider?: NetdiskProvider) => {
    try {
      const response = await apiService.switchUser(username, provider)
      if (response.success) {
        users.value.forEach(user => {
          user.is_current = user.username === username && (!provider || user.provider === provider)
          if (response.current_user?.quota && user.username === username) {
            user.quota = {
              ...response.current_user.quota,
              used_formatted: `${response.current_user.quota.used_gb || 0} GB`,
              total_formatted: `${response.current_user.quota.total_gb || 0} GB`
            }
          }
        })
        currentUser.value = username
        await fetchUserQuota()
        return true
      }
      throw new Error(response.message || '\u5207\u6362\u7528\u6237\u5931\u8d25')
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
      }
      throw new Error(response.message || '\u83b7\u53d6\u7528\u6237 Cookies \u5931\u8d25')
    } catch (err) {
      error.value = getErrorMessage(err)
      throw err
    }
  }

  const updateQuarkSigninConfig = async (data: QuarkSigninConfigRequest) => {
    try {
      const response = await apiService.updateQuarkSigninConfig(data)
      if (!response.success) {
        throw new Error(response.message || '\u4fdd\u5b58\u5938\u514b\u7b7e\u5230\u914d\u7f6e\u5931\u8d25')
      }
      await fetchUsers()
      return true
    } catch (err) {
      error.value = getErrorMessage(err)
      throw err
    }
  }

  const runQuarkSignin = async (username: string): Promise<QuarkSigninResult> => {
    try {
      const response = await apiService.runQuarkSignin(username)
      const result = response.result || response.data?.result
      if (!response.success || !result) {
        throw new Error(response.message || '\u5938\u514b\u7b7e\u5230\u5931\u8d25')
      }
      await fetchUsers()
      return result
    } catch (err) {
      error.value = getErrorMessage(err)
      await fetchUsers()
      throw err
    }
  }

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

  const init = async () => {
    await fetchUsers()
    await fetchUserQuota()
  }

  return {
    users,
    currentUser,
    userQuota,
    loading,
    error,
    currentUserInfo,
    validUsers,
    invalidUsers,
    userStats,
    fetchUsers,
    fetchUserQuota,
    addUser,
    updateUser,
    deleteUser,
    switchUser,
    getUserCookies,
    updateQuarkSigninConfig,
    runQuarkSignin,
    findUserByUsername,
    isCurrentUser,
    updateUserStatus,
    clearError,
    init
  }
})
