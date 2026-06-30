<template>
  <el-dialog
    v-model="visible"
    :title="editingTask ? '编辑任务' : '添加任务'"
    width="650px"
    :close-on-click-modal="false"
    class="add-task-dialog"
    :lock-scroll="false"
  >
    <el-form
      ref="formRef"
      :model="form"
      :rules="formRules"
      label-width="80px"
      @submit.prevent="handleSubmit"
    >
      <el-form-item label="网盘类型" prop="provider">
        <el-select v-model="form.provider" :disabled="!!editingTask" style="width: 100%">
          <el-option
            v-for="provider in providerOptions"
            :key="provider.value"
            :label="provider.label"
            :value="provider.value"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="使用账号" prop="account">
        <el-select
          v-model="form.account"
          :placeholder="providerUsers.length ? '请选择账号' : '请先在用户管理中添加账号'"
          style="width: 100%"
          clearable
        >
          <el-option
            v-for="user in providerUsers"
            :key="`${user.provider}:${user.username}`"
            :label="user.username"
            :value="user.username"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="任务名称" prop="name">
        <el-input
          v-model="form.name"
          placeholder="可选，用于标识任务"
          clearable
          @input="pathNameSync && handlePathNameSync()"
        />
      </el-form-item>
      
      <el-form-item label="分享链接" prop="url">
        <el-input
          v-model="form.url"
          :placeholder="sharePlaceholder"
          clearable
          @blur="parseUrl"
          :loading="isParsingUrl"
        />
        <div class="form-help">提取码可以放在链接中，也可以单独填写。</div>
      </el-form-item>
      
      <el-form-item label="保存路径" prop="save_dir">
        <div class="path-input-group">
          <el-autocomplete
            v-model="form.save_dir"
            :fetch-suggestions="searchSavePaths"
            placeholder="例如：/我的资源/电影"
            clearable
            value-key="value"
            class="path-select"
          />
          <el-switch
            v-model="pathNameSync"
            class="sync-switch"
            size="small"
            :title="pathNameSync ? '与任务名称同步' : '不与任务名称同步'"
            @change="handlePathNameSync"
          />
        </div>
      </el-form-item>
      
      <el-form-item label="分类" prop="category">
        <el-autocomplete
          v-model="form.category"
          :fetch-suggestions="searchCategories"
          placeholder="可选，用于给任务分组"
          clearable
          value-key="value"
          style="width: 100%"
        />
      </el-form-item>

      <el-form-item label="定时规则" prop="cron">
            <div class="cron-input-group">
              <el-autocomplete
                v-model="form.cron"
                :fetch-suggestions="searchCronRules"
                placeholder="可选 Cron 表达式，例如 */5 * * * *"
                clearable
                value-key="value"
                class="cron-select"
              />
              <el-button @click="showCronHelper" size="small">Cron 帮助</el-button>
            </div>
            <div class="form-help">留空则使用默认定时规则。*/5 * * * * 表示每 5 分钟执行一次。</div>
          </el-form-item>

          <el-form-item label="文件过滤" prop="regex_pattern">
            <el-autocomplete
              v-model="form.regex_pattern"
              :fetch-suggestions="searchRegexPatterns"
              placeholder="例如 ^(\d+)\.mp4$，用于匹配需要转存的文件"
              clearable
              value-key="value"
              style="width: 100%"
            />
            <div class="form-help">用正则表达式匹配文件，留空则转存全部文件。</div>
          </el-form-item>

          <el-form-item label="重命名规则" prop="regex_replace">
            <el-autocomplete
              v-model="form.regex_replace"
              :fetch-suggestions="searchRegexReplaces"
              placeholder="例如：第 $1 集.mp4"
              clearable
              value-key="value"
              style="width: 100%"
            />
            <div class="form-help">正则替换规则，用于重命名文件，留空则保持原文件名。</div>
          </el-form-item>
    </el-form>
    
    <template #footer>
      <div class="dialog-footer">
        <el-button @click="handleCancel">取消</el-button>
        <el-button
          type="primary"
          :loading="submitting"
          @click="handleSubmit"
        >
          {{ editingTask ? '更新' : '添加' }}
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, watch, reactive, computed, nextTick, onMounted } from 'vue'
import { ElMessage, type FormInstance } from 'element-plus'
import { storeToRefs } from 'pinia'
import { useTaskStore } from '@/stores/tasks'
import { useUserStore } from '@/stores/users'
import { apiService } from '@/services'
import type { Task, NetdiskProvider } from '@/types'

// Props
interface Props {
  modelValue: boolean
  task?: Task | null
}

interface Emits {
  (e: 'update:modelValue', value: boolean): void
  (e: 'success'): void
}

const props = withDefaults(defineProps<Props>(), {
  task: null
})

const emit = defineEmits<Emits>()

// Composables
const taskStore = useTaskStore()
const userStore = useUserStore()
const { 
  taskSavePaths, 
  taskCategories, 
  taskCronRules, 
  taskRegexPatterns, 
  taskRegexReplaces,
  getDefaultSavePath
} = storeToRefs(taskStore)
const { users } = storeToRefs(userStore)

// 状
const formRef = ref<FormInstance>()
const submitting = ref(false)
const pathNameSync = ref(true) // 路径和名称同步开
const isParsingUrl = ref(false) // URL解析状

const form = reactive({
  provider: 'baidu' as NetdiskProvider,
  account: '',
  name: '',
  url: '',
  save_dir: '',
  category: '',
  cron: '',
  regex_pattern: '',
  regex_replace: ''
})

const providerOptions: Array<{ label: string; value: NetdiskProvider }> = [
  { label: '\u767e\u5ea6\u7f51\u76d8', value: 'baidu' },
  { label: '\u5938\u514b\u7f51\u76d8', value: 'quark' },
  { label: '\u963f\u91cc\u4e91\u76d8', value: 'aliyun' },
  { label: 'UC\u7f51\u76d8', value: 'uc' },
  { label: '\u8fc5\u96f7\u7f51\u76d8', value: 'xunlei' }
]

const providerUsers = computed(() => users.value.filter(user => user.provider === form.provider))
const sharePlaceholder = computed(() => {
  const placeholders: Record<NetdiskProvider, string> = {
    baidu: 'https://pan.baidu.com/s/xxx?pwd=1234',
    quark: 'https://pan.quark.cn/s/xxx?pwd=1234',
    aliyun: 'https://www.alipan.com/s/xxx',
    uc: 'https://drive.uc.cn/s/xxx',
    xunlei: 'https://pan.xunlei.com/s/xxx'
  }
  return placeholders[form.provider]
})

// 高级设置折叠面板状
// 移除advancedVisible，不再需要折叠面

const formRules = {
  provider: [
    { required: true, message: '请选择网盘类型', trigger: 'change' }
  ],
  account: [
    { required: true, message: '请选择账号', trigger: 'change' }
  ],
  url: [
    { required: true, message: '请输入分享链接', trigger: 'blur' },
    {
      validator: (_rule: any, value: string, callback: (error?: Error) => void) => {
        const patterns: Record<NetdiskProvider, RegExp> = {
          baidu: /^https?:\/\/pan\.baidu\.com\/(s|share\/init)[/?][a-zA-Z0-9_=&?-]+(?:[?#].*)?$/,
          quark: /^https?:\/\/pan\.quark\.cn\/s\/[A-Za-z0-9_-]+(?:[?#].*)?$/,
          aliyun: /^https?:\/\/(www\.)?(alipan|aliyundrive)\.com\/s\/[A-Za-z0-9_-]+(?:[?#].*)?$/,
          uc: /^https?:\/\/drive\.uc\.cn\/s\/[A-Za-z0-9_-]+(?:[?#].*)?$/,
          xunlei: /^https?:\/\/pan\.xunlei\.com\/s\/[A-Za-z0-9_-]+(?:[?#].*)?$/
        }
        const valid = patterns[form.provider].test(value)
        callback(valid ? undefined : new Error('请输入有效的分享链接'))
      },
      trigger: 'blur'
    }
  ],
  save_dir: [
    { required: true, message: '请输入保存路径', trigger: 'blur' }
  ]
}

// 计算属
const visible = computed({
  get: () => props.modelValue,
  set: (value) => emit('update:modelValue', value)
})

const editingTask = computed(() => props.task)

// 方法
const resetForm = () => {
  form.provider = 'baidu'
  form.account = users.value.find(user => user.provider === form.provider && user.is_current)?.username || ''
  form.name = ''
  form.url = ''
  form.save_dir = getDefaultSavePath.value || '' // 使用默认路径，如果为空则用空字符
  form.category = ''
  form.cron = ''
  form.regex_pattern = ''
  form.regex_replace = ''
  pathNameSync.value = true // 重置开关状
  formRef.value?.resetFields()
}

// 解析转存链接获取文件
const parseUrl = async () => {
  if (!form.url || isParsingUrl.value) return
  
  try {
    isParsingUrl.value = true
    
    // 解析URL和密
    let url = form.url.split('#')[0] // 移除hash部分
    let pwd = ''
    
    if (url.includes('?pwd=')) {
      [url, pwd] = url.split('?pwd=')
    } else if (url.includes('&pwd=')) {
      [url, pwd] = url.split('&pwd=')
    }
    
    const response = await apiService.getShareInfo(url, pwd, form.provider, form.account)
    
    if (response.success && response.folder_name) {
      const filename = response.folder_name
      
      // 自动填充任务名称
      if (!form.name) {
        form.name = filename
      }
      
      // 如果开启了路径和名称同步，更新保存路径
      if (pathNameSync.value && filename) {
        const basePath = getDefaultSavePath.value || ''
        // 修复路径拼接问题，避免出//
        const cleanBasePath = basePath.replace(/\/+$/, '') // 移除末尾的所有斜
        form.save_dir = cleanBasePath ? `${cleanBasePath}/${filename}` : `/${filename}`
      }
    }
  } catch (error) {
    // 静默失败，不显示错误信息
    console.warn('URL parse failed:', error)
  } finally {
    isParsingUrl.value = false
  }
}

// 处理路径和名称同
const handlePathNameSync = () => {
  if (!pathNameSync.value || !form.name) return
  
  const basePath = getDefaultSavePath.value || ''
  // 修复路径拼接问题，避免出//
  const cleanBasePath = basePath.replace(/\/+$/, '') // 移除末尾的所有斜
  form.save_dir = cleanBasePath ? `${cleanBasePath}/${form.name}` : `/${form.name}`
}

// 自动补全搜索函数
const searchSavePaths = (queryString: string, callback: (suggestions: any[]) => void) => {
  const suggestions = taskSavePaths.value
    .filter(path => path.toLowerCase().includes(queryString.toLowerCase()))
    .map(path => ({ value: path }))
  callback(suggestions)
}

const searchCategories = (queryString: string, callback: (suggestions: any[]) => void) => {
  const suggestions = taskCategories.value
    .filter(category => category.toLowerCase().includes(queryString.toLowerCase()))
    .map(category => ({ value: category }))
  callback(suggestions)
}

const searchCronRules = (queryString: string, callback: (suggestions: any[]) => void) => {
  const commonCrons = [
    '*/5 * * * *',   // 5分钟
    '0 * * * *',     // 每小
    '0 0 * * *',     // 每天
    '0 0 * * 0',     // 每周
    '0 0 1 * *'      // 每月
  ]
  
  const allCrons = [...new Set([...commonCrons, ...taskCronRules.value])]
  const suggestions = allCrons
    .filter(cron => cron.toLowerCase().includes(queryString.toLowerCase()))
    .map(cron => ({ value: cron }))
  callback(suggestions)
}

const searchRegexPatterns = (queryString: string, callback: (suggestions: any[]) => void) => {
  const commonPatterns = [
    '^(\\d+)\\.mp4$',           // 数字命名的mp4文件
    '^.*\\.(mp4|mkv|avi)$',     // 视频文件
    '^.*\\.(jpg|png|gif)$',     // 图片文件
    '^.*\\.pdf$'                // PDF文件
  ]
  
  const allPatterns = [...new Set([...commonPatterns, ...taskRegexPatterns.value])]
  const suggestions = allPatterns
    .filter(pattern => pattern.toLowerCase().includes(queryString.toLowerCase()))
    .map(pattern => ({ value: pattern }))
  callback(suggestions)
}

const searchRegexReplaces = (queryString: string, callback: (suggestions: any[]) => void) => {
  const commonReplaces = [
    'Episode $1.mp4',
    'S01E$1.mp4',              // 美剧格式
    '$1.mp4'
  ]
  
  const allReplaces = [...new Set([...commonReplaces, ...taskRegexReplaces.value])]
  const suggestions = allReplaces
    .filter(replace => replace.toLowerCase().includes(queryString.toLowerCase()))
    .map(replace => ({ value: replace }))
  callback(suggestions)
}

const loadTaskData = (task: Task) => {
  form.provider = task.provider || 'baidu'
  form.account = task.account || users.value.find(user => user.provider === form.provider && user.is_current)?.username || ''
  form.name = task.name || ''
  
  // 构建完整的转存链接（包括密码
  let fullUrl = task.url
  if (task.pwd && task.pwd.trim() !== '' && !task.url.includes('?pwd=') && !task.url.includes('&pwd=')) {
    const separator = task.url.includes('?') ? '&' : '?'
    fullUrl = `${task.url}${separator}pwd=${task.pwd}`
  }
  form.url = fullUrl
  
  form.save_dir = task.save_dir
  form.category = task.category || ''
  form.cron = task.cron || ''
  form.regex_pattern = task.regex_pattern || ''
  form.regex_replace = task.regex_replace || ''
  
  // 编辑任务时禁用同步开关，避免意外修改路径
  pathNameSync.value = false
  
  // 如果有高级设置数据，展开面板
  if (task.cron || task.regex_pattern || task.regex_replace) {
  }
}

// Cron助手功能
const showCronHelper = () => {
  ElMessage({
    type: 'info',
    duration: 5000,
    dangerouslyUseHTMLString: true,
    message: `
      <div style="text-align: left;">
        <strong>常用 Cron 表达式：</strong><br/>
        - */5 * * * * - 每 5 分钟<br/>
        - 0 */1 * * * - 每小时<br/>
        - 0 0 * * * - 每天 00:00<br/>
        - 0 0 */3 * * - 每 3 天 00:00<br/>
        - 0 0 * * 0 - 每周日 00:00
      </div>
    `
  })
}

const handleSubmit = async () => {
  if (!formRef.value) return

  const cronParts = form.cron.trim().split(/\s+/).filter(Boolean)
  if (cronParts.length > 5) {
    form.cron = cronParts.slice(0, 5).join(' ')
  }

  const valid = await formRef.value.validate().catch(() => false)
  if (!valid) return

  submitting.value = true

  try {
    if (editingTask.value) {
      await taskStore.updateTask(editingTask.value.order - 1, form)
      ElMessage.success('任务已更新')
    } else {
      await taskStore.addTask(form)
      ElMessage.success('任务已添加')
    }

    visible.value = false
    resetForm()
    emit('success')
  } catch (error) {
    ElMessage.error(`操作失败：${error}`)
  } finally {
    submitting.value = false
  }
}

const handleCancel = () => {
  visible.value = false
  resetForm()
}

// 监听任务数据变化
watch(
  () => form.provider,
  () => {
    if (editingTask.value) return
    const matched = users.value.find(user => user.provider === form.provider && user.username === form.account)
    if (!matched) {
      form.account = users.value.find(user => user.provider === form.provider && user.is_current)?.username || providerUsers.value[0]?.username || ''
    }
  }
)

watch(
  providerUsers,
  (nextUsers) => {
    if (!form.account && nextUsers.length > 0) {
      form.account = nextUsers.find(user => user.is_current)?.username || nextUsers[0].username
    }
  }
)

onMounted(() => {
  userStore.fetchUsers()
})

watch(
  () => props.task,
  (newTask) => {
    // 使用nextTick确保DOM更新完成后再操作
    nextTick(() => {
      if (newTask) {
        loadTaskData(newTask)
      } else {
        // 强制重置表单，确保状态清
        resetForm()
      }
    })
  },
  { immediate: true }
)

// 应用移动端样 - 优化版本
const applyMobileStyles = () => {
  if (window.innerWidth <= 1200) { // 使用统一断点
    nextTick(() => {
      // 确保底部按钮不被地址栏遮
      const footer = document.querySelector('.add-task-dialog .el-dialog__footer')
      if (footer) {
        const footerElement = footer as HTMLElement
        // 使用fixed定位，确保始终在视口底部
        footerElement.style.setProperty('position', 'fixed', 'important')
        footerElement.style.setProperty('bottom', '0', 'important')
        footerElement.style.setProperty('left', '0', 'important')
        footerElement.style.setProperty('right', '0', 'important')
        footerElement.style.setProperty('z-index', '10001', 'important')
        footerElement.style.setProperty('background', 'white', 'important')
        footerElement.style.setProperty('box-shadow', '0 -2px 8px rgba(0, 0, 0, 0.1)', 'important')
        // 适配安全区域
        const safeAreaBottom = getComputedStyle(document.documentElement).getPropertyValue('env(safe-area-inset-bottom)') || '20px'
        footerElement.style.setProperty('padding-bottom', `calc(16px + ${safeAreaBottom})`, 'important')
      }
      
      // 调整内容区域，为底部按钮留出空间
      const body = document.querySelector('.add-task-dialog .el-dialog__body')
      if (body) {
        const bodyElement = body as HTMLElement
        bodyElement.style.setProperty('padding-bottom', '120px', 'important') // 更多底部间距
        bodyElement.style.setProperty('height', 'calc(100vh - 160px)', 'important')
      }
    })
  }
}

// 监听对话框显示状
watch(visible, (newVisible) => {
  if (!newVisible) {
    resetForm()
  } else {
    // 对话框打开时，如果没有编辑任务，重置表
    if (!props.task) {
      // 使用nextTick确保DOM更新完成后再重置
      nextTick(() => {
        resetForm()
      })
    }
    // 应用移动端样
    applyMobileStyles()
  }
})

// 监听任务名称变化，自动同步到保存路径
watch(() => form.name, (newName) => {
  if (pathNameSync.value && newName) {
    handlePathNameSync()
  }
})

// 监听同步开关变
watch(pathNameSync, (newValue) => {
  if (newValue && form.name) {
    handlePathNameSync()
  }
})
</script>

<style scoped>
.add-task-dialog :deep(.el-dialog__header) {
  padding: 20px 20px 10px;
  border-bottom: 1px solid #e4e7ed;
}

.add-task-dialog :deep(.el-dialog__body) {
  padding: 20px;
}

.add-task-dialog :deep(.el-dialog__footer) {
  padding: 10px 20px 20px;
  border-top: 1px solid #e4e7ed;
}

.dialog-footer {
  display: flex;
  justify-content: flex-end;
  gap: 12px;
}

.el-form-item {
  margin-bottom: 20px;
}

.el-form-item :deep(.el-form-item__label) {
  font-weight: 500;
  color: #606266;
}

.el-textarea :deep(.el-textarea__inner) {
  resize: vertical;
  min-height: 80px;
}

/* 高级设置区域样式 */
.advanced-settings {
  margin-top: 20px;
}

.form-help {
  font-size: 12px;
  color: #909399;
  margin-top: 5px;
  line-height: 1.4;
}

.path-input-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.path-select {
  flex: 1;
}

.cron-input-group {
  display: flex;
  align-items: center;
  gap: 12px;
}

.cron-select {
  flex: 1;
}

.sync-switch {
  flex-shrink: 0;
}

.sync-switch :deep(.el-switch__core) {
  background-color: #dcdfe6;
}

.sync-switch :deep(.is-checked .el-switch__core) {
  background-color: #409eff;
}

/* 确保对话框在移动端有正确的层 */
:deep(.el-overlay) {
  z-index: 9999 !important;
  background-color: rgba(0, 0, 0, 0.5) !important;
}

.add-task-dialog {
  z-index: 10000 !important;
}

/* 响应式调 - 统一断点1200px */
@media (max-width: 1200px) {
  :deep(.el-overlay) {
    padding: 0 !important;
  }
  
  /* 直接覆盖Element Plus的dialog样式 */
  :deep(.el-dialog.add-task-dialog) {
    width: 100vw !important;
    max-width: 100vw !important;
    margin: 0 !important;
    border-radius: 0 !important;
    height: 100vh !important;
    max-height: 100vh !important;
    z-index: 10000 !important;
    overflow: hidden !important;
    position: fixed !important;
    top: 0 !important;
    left: 0 !important;
    right: 0 !important;
    bottom: 0 !important;
  }
  
  :deep(.el-dialog.add-task-dialog .el-dialog__header) {
    padding: 16px 20px 10px 20px !important;
    border-bottom: 1px solid #f0f0f0;
  }
  
  :deep(.el-dialog.add-task-dialog .el-dialog__body) {
    padding: 16px 20px 100px 20px !important; /* 增加底部padding为按钮和安全区域留空 */
    height: calc(100vh - 140px) !important; /* 减少高度为按钮留更多空间 */
    overflow-y: auto !important;
    box-sizing: border-box !important;
  }
  
  :deep(.el-dialog.add-task-dialog .el-dialog__footer) {
    padding: 16px 20px !important;
    padding-bottom: calc(16px + env(safe-area-inset-bottom, 20px)) !important; /* 适配安全区域 */
    border-top: 1px solid #f0f0f0;
    position: fixed !important; /* 使用fixed确保始终在视口底 */
    bottom: 0 !important;
    left: 0 !important;
    right: 0 !important;
    background: white !important;
    display: flex !important;
    justify-content: flex-end !important;
    align-items: center !important;
    gap: 12px !important;
    z-index: 10001 !important; /* 确保在最上层 */
    box-shadow: 0 -2px 8px rgba(0, 0, 0, 0.1) !important; /* 添加阴影效果 */
    min-height: 70px !important; /* 确保按钮区域有足够高 */
  }
  
  /* 表单标签调整 */
  :deep(.el-dialog.add-task-dialog .el-form-item__label) {
    width: 80px !important;
    font-size: 14px !important;
    line-height: 1.4 !important;
  }
  
  /* 表单内容区域 */
  :deep(.el-dialog.add-task-dialog .el-form-item__content) {
    margin-left: 80px !important;
  }
  
  /* 移动端优化表单按 */
  :deep(.el-dialog.add-task-dialog .el-button) {
    min-height: 44px !important;
    padding: 12px 24px !important;
    border-radius: 8px !important;
    font-size: 16px !important;
    font-weight: 500 !important;
    min-width: 80px !important;
  }
  
  /* 底部按钮特别样式 */
  :deep(.el-dialog.add-task-dialog .el-dialog__footer .el-button) {
    box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1) !important;
  }
  
  /* 取消按钮样式 */
  :deep(.el-dialog.add-task-dialog .el-dialog__footer .el-button--default) {
    background: #f5f7fa !important;
    border-color: #e4e7ed !important;
    color: #606266 !important;
  }
  
  /* 主要操作按钮样式 */
  :deep(.el-dialog.add-task-dialog .el-dialog__footer .el-button--primary) {
    background: #409eff !important;
    border-color: #409eff !important;
    color: white !important;
  }
  
  /* 移动端优化表单输入框 */
  :deep(.el-dialog.add-task-dialog .el-input),
  :deep(.el-dialog.add-task-dialog .el-textarea) {
    width: 100% !important;
  }
  
  :deep(.el-dialog.add-task-dialog .el-input__inner),
  :deep(.el-dialog.add-task-dialog .el-textarea__inner) {
    min-height: 44px !important;
    font-size: 16px !important; /* 防止iOS放大 */
    width: 100% !important;
    box-sizing: border-box !important;
    padding: 12px !important;
    border-radius: 6px !important;
    word-break: break-all !important;
    overflow-wrap: break-word !important;
  }
  
  /* 移动端表单项优化 */
  :deep(.el-dialog.add-task-dialog .el-form-item) {
    margin-bottom: 20px !important;
  }
  
  /* 帮助文本优化 */
  :deep(.el-dialog.add-task-dialog) .form-help {
    font-size: 12px !important;
    line-height: 1.4 !important;
    margin-top: 6px !important;
  }
  
  /* 高级设置按钮 */
  :deep(.el-dialog.add-task-dialog .advanced-toggle) {
    width: 100% !important;
    margin-top: 8px !important;
  }
}
</style>
