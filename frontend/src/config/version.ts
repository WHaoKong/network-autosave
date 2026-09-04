// version config
export const VERSION_CONFIG = {
  APP_VERSION: __APP_VERSION__,
  BUILD_TIME: __BUILD_TIME__,
  RELEASE_NOTES: 'network-autosave 1.1.0：夸克每日签到、通知标题显示任务结果',
  UPDATE_NOTES: {
    'v1.1.0': '新增夸克每日签到领空间；通知内容改为任务名称+成功/失败；修复右上角显示登录用户名与中文乱码',
    'v1.0.0': '多网盘自动转存工具 network-autosave 初始版本',
  }
} as const

export const APP_VERSION = VERSION_CONFIG.APP_VERSION
export const BUILD_TIME = VERSION_CONFIG.BUILD_TIME
export const RELEASE_NOTES = VERSION_CONFIG.RELEASE_NOTES
