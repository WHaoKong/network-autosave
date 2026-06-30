<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <h1 class="login-title">&#32593;&#30424;&#33258;&#21160;&#36716;&#23384;&#24037;&#20855;</h1>
        <p class="login-subtitle">&#35831;&#30331;&#24405;&#24744;&#30340;&#36134;&#25143;</p>
      </div>

      <form class="login-form" @submit.prevent="handleLogin">
        <div class="login-field">
          <input
            v-model="loginForm.username"
            name="username"
            type="text"
            autocomplete="username"
            placeholder="&#29992;&#25143;&#21517;"
            class="login-input"
            :disabled="loading"
          />
        </div>

        <div class="login-field">
          <input
            v-model="loginForm.password"
            name="current-password"
            type="password"
            autocomplete="current-password"
            placeholder="&#23494;&#30721;"
            class="login-input"
            :disabled="loading"
          />
        </div>

        <div class="login-button-item">
          <el-button
            type="primary"
            size="large"
            class="login-button"
            :loading="loading"
            native-type="submit"
          >
            {{ loading ? '\u767b\u5f55\u4e2d...' : '\u767b\u5f55' }}
          </el-button>
        </div>
      </form>

      <div class="login-footer">
        <div class="version-info">
          <span>&#29256;&#26412; {{ APP_VERSION }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { ElMessage } from 'element-plus'
import { useAuthStore } from '@/stores/auth'
import { APP_VERSION } from '@/config/version'

const router = useRouter()
const route = useRoute()
const authStore = useAuthStore()

const loading = ref(false)

// Form data
const loginForm = reactive({
  username: '',
  password: ''
})

// Handle login
const handleLogin = async () => {
  if (!loginForm.username.trim()) {
    ElMessage.warning('\u8bf7\u8f93\u5165\u7528\u6237\u540d')
    return
  }
  if (!loginForm.password) {
    ElMessage.warning('\u8bf7\u8f93\u5165\u5bc6\u7801')
    return
  }
  if (loginForm.password.length < 6) {
    ElMessage.warning('\u5bc6\u7801\u957f\u5ea6\u4e0d\u80fd\u5c11\u4e8e6\u4f4d')
    return
  }

  loading.value = true

  try {
    await authStore.login(loginForm.username, loginForm.password)

    ElMessage.success('\u767b\u5f55\u6210\u529f')

    const redirect = route.query.redirect as string
    await router.push(redirect || '/')
  } catch (error) {
    ElMessage.error(`\u767b\u5f55\u5931\u8d25: ${error}`)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.login-card {
  width: 100%;
  max-width: 400px;
  background: white;
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  padding: 40px;
  position: relative;
  overflow: hidden;
}

.login-card::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 4px;
  background: linear-gradient(90deg, #409eff, #67c23a, #e6a23c, #f56c6c);
}

.login-header {
  text-align: center;
  margin-bottom: 40px;
}

.login-title {
  font-size: 24px;
  font-weight: 600;
  color: #333;
  margin-bottom: 8px;
}

.login-subtitle {
  font-size: 14px;
  color: #666;
  margin: 0;
}

.login-form {
  margin-bottom: 20px;
}

.login-field {
  margin-bottom: 24px;
}

.login-input {
  width: 100%;
  min-height: 44px;
  padding: 0 14px;
  font-size: 14px;
  color: #303133;
  background: #fff;
  border: 1px solid #dcdfe6;
  border-radius: 8px;
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.login-input:focus {
  outline: none;
  border-color: #409eff;
  box-shadow: 0 0 0 2px rgba(64, 158, 255, 0.12);
}

.login-input::placeholder {
  color: #a8abb2;
}

.login-button-item {
  margin-bottom: 0;
}

.login-button {
  width: 100%;
  height: 44px;
  font-size: 16px;
  font-weight: 500;
  border-radius: 8px;
}

.login-footer {
  text-align: center;
  padding-top: 20px;
  border-top: 1px solid #f0f0f0;
}

.version-info {
  font-size: 12px;
  color: #999;
}

@media (max-width: 480px) {
  .login-container {
    padding: 16px;
  }

  .login-card {
    padding: 30px 24px;
  }

  .login-title {
    font-size: 20px;
  }
}

@media (prefers-color-scheme: dark) {
  .login-card {
    background: #2d2d2d;
    color: #fff;
  }

  .login-title {
    color: #fff;
  }

  .login-subtitle,
  .version-info {
    color: #ccc;
  }

  .login-input {
    color: #f5f7fa;
    background: #1f1f1f;
    border-color: #4c4d4f;
  }

  .login-input::placeholder {
    color: #8d9095;
  }

  .login-footer {
    border-top-color: #4c4d4f;
  }
}
</style>
