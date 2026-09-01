<template>
  <div class="users-view">
    <div class="page-header">
      <h1 class="page-title">用户管理</h1>
      <el-button type="primary" @click="openAddUserDialog">
        <el-icon><Plus /></el-icon>
        添加用户
      </el-button>
    </div>

    <!-- 用户统计 -->
    <div class="stats-section">
      <div class="stat-card">
        <div class="stat-content">
          <div class="stat-number">{{ userStats.total }}</div>
          <div class="stat-label">总用户数</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-content">
          <div class="stat-number">{{ userStats.valid }}</div>
          <div class="stat-label">有效用户</div>
        </div>
      </div>
      <div class="stat-card">
        <div class="stat-content">
          <div class="stat-number">{{ userStats.invalid }}</div>
          <div class="stat-label">失效用户</div>
        </div>
      </div>
    </div>

    <!-- 用户列表 -->
    <div class="users-list">
      <el-card v-loading="loading">
        <div class="user-grid">
          <div
            v-for="user in users"
            :key="user.username"
            class="user-card"
            :class="{ 'current-user': user.is_current, 'invalid-user': user.cookies_valid === false }"
          >
            <div class="user-header">
              <div class="user-info">
                <h3 class="username">{{ user.username }}</h3>
                <el-tag size="small">{{ displayProviderName(user.provider) }}</el-tag>
                <el-tag v-if="user.is_current" type="success" size="small">当前</el-tag>
                <el-tag v-else-if="user.cookies_valid === false" type="danger" size="small">失效</el-tag>
                <el-tag
                  v-if="user.provider === 'quark' && user.signin_enabled"
                  type="success"
                  size="small"
                >
                  自动签到
                </el-tag>
              </div>
              <div class="user-actions">
                <el-dropdown trigger="click">
                  <el-button type="text">
                    <el-icon><MoreFilled /></el-icon>
                  </el-button>
                  <template #dropdown>
                    <el-dropdown-menu>
                      <el-dropdown-item v-if="!user.is_current" @click="switchUser(user)">
                        切换用户
                      </el-dropdown-item>
                      <el-dropdown-item @click="editUser(user)">
                        编辑用户
                      </el-dropdown-item>
                      <el-dropdown-item @click="getUserCookies(user)">
                        查看 Cookies
                      </el-dropdown-item>
                      <el-dropdown-item
                        v-if="user.provider === 'quark'"
                        :disabled="signinRunning === user.username || !user.signin_configured"
                        @click="runQuarkSignin(user)"
                      >
                        {{ signinRunning === user.username ? '签到中...' : '立即签到' }}
                      </el-dropdown-item>
                      <el-dropdown-item 
                        v-if="!user.is_current"
                        @click="deleteUser(user)"
                        style="color: #f56c6c"
                      >
                        删除用户
                      </el-dropdown-item>
                    </el-dropdown-menu>
                  </template>
                </el-dropdown>
              </div>
            </div>
            
            <div class="user-quota">
              <div class="quota-info">
                <span class="quota-label">存储空间</span>
                <span v-if="user.quota" class="quota-value">
                  {{ user.quota.used_formatted }} / {{ user.quota.total_formatted }}
                </span>
                <span v-else class="quota-value quota-unknown">暂无数据</span>
              </div>
              <el-progress
                v-if="user.quota && user.quota.total > 0"
                :percentage="Math.min(100, Math.round((user.quota.used / user.quota.total) * 100))"
                :stroke-width="6"
                :show-text="false"
              />
            </div>
            
            <div v-if="user.last_active" class="user-activity">
              <span class="activity-label">最后活跃：</span>
              <span class="activity-time">{{ formatTime(user.last_active) }}</span>
            </div>
            <div v-if="user.provider === 'quark'" class="signin-status">
              <span class="activity-label">签到状态：</span>
              <span>{{ user.signin_meta?.last_message || (user.signin_configured ? '尚未签到' : '未配置凭据') }}</span>
              <span v-if="user.signin_meta?.last_run_at">
                （{{ formatTime(user.signin_meta.last_run_at) }}）
              </span>
            </div>
          </div>
        </div>
      </el-card>
    </div>

    <!-- 添加/编辑用户对话 -->
    <el-dialog
      v-model="showAddUserDialog"
      :title="editingUser ? '编辑用户' : '添加用户'"
      width="600px"
      @closed="resetUserForm"
    >
      <el-form
        ref="userFormRef"
        :model="userForm"
        :rules="userFormRules"
        label-width="100px"
      >
        <el-form-item label="网盘类型" prop="provider">
          <el-select v-model="userForm.provider" :disabled="!!editingUser" style="width: 100%">
            <el-option
              v-for="provider in providerOptions"
              :key="provider.value"
              :label="provider.label"
              :value="provider.value"
            />
          </el-select>
        </el-form-item>

        <el-form-item label="用户名" prop="username">
          <el-input 
            v-model="userForm.username" 
            placeholder="请输入用户名"
            :disabled="!!editingUser"
          />
        </el-form-item>
        
        <el-form-item label="Cookies" prop="cookies">
          <el-input
            v-model="userForm.cookies"
            type="textarea"
            :rows="6"
            placeholder="请在此粘贴 Cookies..."
          />
          <div class="form-help">
            获取方法：打开百度网盘网页版，按F12打开开发者工具，在Network标签下找到任意请求，复制Cookies
          </div>
        </el-form-item>

        <template v-if="userForm.provider === 'quark'">
          <el-divider content-position="left">每日签到领空间</el-divider>
          <el-form-item label="自动签到">
            <el-switch v-model="userForm.signin_enabled" />
          </el-form-item>
          <el-form-item label="kps">
            <el-input
              v-model="userForm.kps"
              type="password"
              show-password
              autocomplete="off"
              :placeholder="editingUser?.signin_configured ? '留空则保留现有值' : '请输入手机客户端抓包参数 kps'"
            />
          </el-form-item>
          <el-form-item label="sign">
            <el-input
              v-model="userForm.sign"
              type="password"
              show-password
              autocomplete="off"
              :placeholder="editingUser?.signin_configured ? '留空则保留现有值' : '请输入手机客户端抓包参数 sign'"
            />
          </el-form-item>
          <el-form-item label="vcode">
            <el-input
              v-model="userForm.vcode"
              type="password"
              show-password
              autocomplete="off"
              :placeholder="editingUser?.signin_configured ? '留空则保留现有值' : '请输入手机客户端抓包参数 vcode'"
            />
            <div class="form-help">
              从夸克手机客户端签到页抓取 drive-m.quark.cn 请求参数。
              <a
                href="https://github.com/Cp0204/quark-auto-save/wiki/%E4%BD%BF%E7%94%A8%E6%8A%80%E5%B7%A7%E9%9B%86%E9%94%A6#%E6%AF%8F%E6%97%A5%E7%AD%BE%E5%88%B0%E9%A2%86%E7%A9%BA%E9%97%B4"
                target="_blank"
                rel="noopener noreferrer"
              >查看抓取说明</a>
            </div>
          </el-form-item>
        </template>
      </el-form>
      
      <template #footer>
        <el-button @click="showAddUserDialog = false">取消</el-button>
        <el-button type="primary" @click="handleUserSubmit" :loading="submitting">
          {{ editingUser ? '更新' : '添加' }}
        </el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { ElMessage, ElMessageBox, type FormInstance } from 'element-plus'
import { storeToRefs } from 'pinia'
import { useUserStore } from '@/stores/users'
import type { User, NetdiskProvider } from '@/types'
import { formatTime } from '@/utils/helpers'

const userStore = useUserStore()
const { users, loading, userStats } = storeToRefs(userStore)

const providerOptions: Array<{ label: string; value: NetdiskProvider }> = [
  { label: '\u767e\u5ea6\u7f51\u76d8', value: 'baidu' },
  { label: '\u5938\u514b\u7f51\u76d8', value: 'quark' },
  { label: '\u963f\u91cc\u4e91\u76d8', value: 'aliyun' },
  { label: 'UC\u7f51\u76d8', value: 'uc' },
  { label: '\u8fc5\u96f7\u7f51\u76d8', value: 'xunlei' }
]

const displayProviderName = (provider?: NetdiskProvider) => {
  return providerOptions.find(option => option.value === provider)?.label || provider || '-'
}

// 表单相关
const showAddUserDialog = ref(false)
const userFormRef = ref<FormInstance>()
const editingUser = ref<User | null>(null)
const submitting = ref(false)
const signinRunning = ref<string | null>(null)

const userForm = ref({
  provider: 'baidu' as NetdiskProvider,
  username: '',
  cookies: '',
  signin_enabled: false,
  kps: '',
  sign: '',
  vcode: ''
})

const userFormRules = {
  username: [
    { required: true, message: '请输入用户名', trigger: 'blur' }
  ],
  cookies: [
    { required: true, message: '请输入Cookies', trigger: 'blur' },
    { min: 100, message: 'Cookies长度不能少于100字符', trigger: 'blur' }
  ]
}

// 方法
const switchUser = async (user: User) => {
  try {
    await userStore.switchUser(user.username, user.provider)
    ElMessage.success(`已切换到用户${user.username}`)
  } catch (error) {
    ElMessage.error(`切换用户失败${error}`)
  }
}

const openAddUserDialog = () => {
  resetUserForm()
  showAddUserDialog.value = true
}

const editUser = async (user: User) => {
  editingUser.value = user
  
  try {
    // 获取用户的完整cookies信息
    const userCookies = await userStore.getUserCookies(user.username, user.provider)
    userForm.value = {
      provider: user.provider || 'baidu',
      username: user.username,
      cookies: userCookies || '',
      signin_enabled: user.signin_enabled || false,
      kps: '',
      sign: '',
      vcode: ''
    }
  } catch (error) {
    // 如果获取cookies失败，使用空字符
    userForm.value = {
      provider: user.provider || 'baidu',
      username: user.username,
      cookies: '',
      signin_enabled: user.signin_enabled || false,
      kps: '',
      sign: '',
      vcode: ''
    }
    console.warn('无法加载用户cookies:', error)
  }
  
  showAddUserDialog.value = true
}

const deleteUser = async (user: User) => {
  try {
    await ElMessageBox.confirm(
      `确定要删除用 ${user.username} 吗？此操作不可恢复。`,
      '确认删除',
      {
        confirmButtonText: '删除',
        cancelButtonText: '取消',
        type: 'warning'
      }
    )
    
    await userStore.deleteUser(user.username, user.provider)
    ElMessage.success('用户已删')
  } catch (error) {
    if (error !== 'cancel') {
      ElMessage.error(`删除用户失败${error}`)
    }
  }
}

const getUserCookies = async (user: User) => {
  try {
    const cookies = await userStore.getUserCookies(user.username, user.provider)
    
    ElMessageBox.alert(
      cookies,
      `用户 ${user.username} 的Cookies`,
      {
        confirmButtonText: '复制',
        callback: async () => {
          try {
            await navigator.clipboard.writeText(cookies)
            ElMessage.success('Cookies已复制到剪贴')
          } catch {
            ElMessage.warning('复制失败，请手动复制')
          }
        }
      }
    )
  } catch (error) {
    ElMessage.error(`获取Cookies失败${error}`)
  }
}

const runQuarkSignin = async (user: User) => {
  signinRunning.value = user.username
  try {
    const result = await userStore.runQuarkSignin(user.username)
    const rewardMb = ((result.reward_bytes || 0) / (1024 ** 2)).toFixed(2)
    const rewardText = result.reward_bytes ? `，奖励 ${rewardMb} MB` : ''
    ElMessage.success(`${result.message}${rewardText}`)
  } catch (error) {
    ElMessage.error(`签到失败：${error}`)
  } finally {
    signinRunning.value = null
  }
}

const handleUserSubmit = async () => {
  if (!userFormRef.value) return

  const valid = await userFormRef.value.validate().catch(() => false)
  if (!valid) return

  if (
    userForm.value.provider === 'quark'
    && userForm.value.signin_enabled
    && !editingUser.value?.signin_configured
    && (!userForm.value.kps || !userForm.value.sign || !userForm.value.vcode)
  ) {
    ElMessage.warning('启用自动签到前请完整填写 kps、sign、vcode')
    return
  }

  submitting.value = true

  try {
    if (editingUser.value) {
      await userStore.updateUser({
        provider: userForm.value.provider,
        original_username: editingUser.value.username,
        username: userForm.value.username,
        cookies: userForm.value.cookies
      })
      ElMessage.success('用户信息已更')
    } else {
      await userStore.addUser(userForm.value)
      ElMessage.success('用户已添')
    }

    if (userForm.value.provider === 'quark') {
      await userStore.updateQuarkSigninConfig({
        username: userForm.value.username,
        enabled: userForm.value.signin_enabled,
        kps: userForm.value.kps,
        sign: userForm.value.sign,
        vcode: userForm.value.vcode
      })
    }

    showAddUserDialog.value = false
    resetUserForm()
  } catch (error) {
    ElMessage.error(`操作失败${error}`)
  } finally {
    submitting.value = false
  }
}

const resetUserForm = () => {
  editingUser.value = null
  userForm.value = {
    provider: 'baidu',
    username: '',
    cookies: '',
    signin_enabled: false,
    kps: '',
    sign: '',
    vcode: ''
  }
  userFormRef.value?.resetFields()
}

onMounted(async () => {
  await userStore.init()
})
</script>

<style scoped>
.users-view {
  padding: 24px;
  min-height: 100vh;
  background-color: #f5f5f5;
}

.page-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
}

.page-title {
  font-size: 24px;
  font-weight: 600;
  color: #333;
  margin: 0;
}

.stats-section {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 20px;
  margin-bottom: 24px;
}

.stat-card {
  background: white;
  padding: 24px;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
  text-align: center;
}

.stat-number {
  font-size: 28px;
  font-weight: 600;
  color: #409eff;
  margin-bottom: 8px;
}

.stat-label {
  font-size: 14px;
  color: #666;
}

.users-list {
  background: white;
  border-radius: 8px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
}

.user-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
  gap: 20px;
  padding: 20px;
}

.user-card {
  border: 2px solid #e4e7ed;
  border-radius: 8px;
  padding: 20px;
  transition: all 0.3s;
}

.user-card:hover {
  border-color: #409eff;
  box-shadow: 0 4px 12px rgba(64, 158, 255, 0.1);
}

.user-card.current-user {
  border-color: #67c23a;
  background-color: #f0f9ff;
}

.user-card.invalid-user {
  border-color: #f56c6c;
  background-color: #fef0f0;
}

.user-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 16px;
}

.user-info {
  flex: 1;
}

.username {
  font-size: 18px;
  font-weight: 600;
  color: #333;
  margin-bottom: 8px;
}

.user-quota {
  margin-bottom: 12px;
}

.quota-info {
  display: flex;
  justify-content: space-between;
  margin-bottom: 8px;
  font-size: 14px;
}

.quota-label {
  color: #666;
}

.quota-value {
  font-weight: 500;
  color: #333;
}

.quota-unknown {
  color: #909399;
  font-weight: 400;
}

.user-activity {
  font-size: 12px;
  color: #999;
}

.signin-status {
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
}

.activity-label {
  margin-right: 4px;
}

.form-help {
  font-size: 12px;
  color: #909399;
  margin-top: 4px;
  line-height: 1.4;
}

/* 响应式设 */
@media (max-width: 768px) {
  .users-view {
    padding: 16px;
  }
  
  .page-header {
    flex-direction: column;
    gap: 16px;
    align-items: stretch;
  }
  
  .user-grid {
    grid-template-columns: 1fr;
    padding: 16px;
    gap: 16px;
  }
}
</style>
