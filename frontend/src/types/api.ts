export interface ApiResponse<T = any> {
  success: boolean
  message?: string
  data?: T
  [key: string]: any
}

export type NetdiskProvider = 'baidu' | 'quark' | 'aliyun' | 'uc' | 'xunlei'

export interface Task {
  order: number
  task_uid?: string
  provider?: NetdiskProvider
  account?: string
  name?: string
  url: string
  save_dir: string
  pwd?: string
  status: 'normal' | 'error' | 'running' | 'success' | 'failed' | 'completed' | 'skipped'
  message?: string
  progress?: number
  category?: string
  cron?: string
  regex_pattern?: string
  regex_replace?: string
  share_info?: ShareInfo
  created_at?: string
  updated_at?: string
  last_execute_time?: number
  transferred_files?: string[]
}

export interface ShareInfo {
  url: string
  password?: string
  expires_at?: string
}

export interface CreateTaskRequest {
  provider?: NetdiskProvider
  account?: string
  url: string
  save_dir: string
  pwd?: string
  name?: string
  category?: string
  cron?: string
  regex_pattern?: string
  regex_replace?: string
}

export interface UpdateTaskRequest {
  provider?: NetdiskProvider
  account?: string
  url?: string
  save_dir?: string
  pwd?: string
  name?: string
  category?: string
  cron?: string
  regex_pattern?: string
  regex_replace?: string
}

export interface TaskOperation {
  type: 'execute' | 'edit' | 'delete' | 'share'
  taskId: number
}

export interface BatchOperation {
  type: 'execute' | 'delete'
  taskIds: number[]
}

export interface User {
  username: string
  provider?: NetdiskProvider
  is_current: boolean
  quota?: UserQuota
  cookies_valid?: boolean
  last_active?: string
  signin_enabled?: boolean
  signin_configured?: boolean
  signin_meta?: QuarkSigninMeta | null
}

export interface QuarkSigninMeta {
  last_run_at?: string
  last_sign_date?: string | null
  last_reward_bytes?: number
  last_status?: string
  last_message?: string
}

export interface QuarkSigninConfigRequest {
  username: string
  enabled: boolean
  kps?: string
  sign?: string
  vcode?: string
}

export interface QuarkSigninResult {
  account: string
  success: boolean
  already_signed?: boolean
  reward_bytes?: number
  status: string
  message: string
  sign_progress?: number
  sign_target?: number
  total_capacity?: number
}

export interface UserQuota {
  used: number
  total: number
  used_formatted: string
  total_formatted: string
  percent: number
}

export interface CreateUserRequest {
  provider?: NetdiskProvider
  username: string
  cookies: string
}

export interface UpdateUserRequest {
  provider?: NetdiskProvider
  original_username: string
  username: string
  cookies: string
}

export interface Config {
  notifications: NotificationConfig
  scheduling: SchedulingConfig
  sharing: SharingConfig
  general: GeneralConfig
}

export interface NotificationConfig {
  enabled: boolean
  webhook_url?: string
  custom_fields?: Record<string, string>
}

export interface SchedulingConfig {
  enabled: boolean
  interval: number
  start_time?: string
  end_time?: string
}

export interface SharingConfig {
  enabled: boolean
  default_password: boolean
  default_period: number
}

export interface GeneralConfig {
  max_retries: number
  timeout: number
  concurrent_limit: number
}

export interface LogEntry {
  timestamp: string
  level: 'INFO' | 'WARNING' | 'ERROR' | 'DEBUG'
  message: string
  module?: string
}

export interface VersionInfo {
  current: string
  latest: string
  has_update: boolean
  update_url?: string
  release_notes?: string
}
