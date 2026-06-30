// version config
export const VERSION_CONFIG = {
  APP_VERSION: __APP_VERSION__,
  BUILD_TIME: __BUILD_TIME__,
  RELEASE_NOTES: 'network-autosave 1.0.0 initial release',
  UPDATE_NOTES: {
    'v1.0.0': 'Multi-provider network autosave initial release',
  }
} as const

export const APP_VERSION = VERSION_CONFIG.APP_VERSION
export const BUILD_TIME = VERSION_CONFIG.BUILD_TIME
export const RELEASE_NOTES = VERSION_CONFIG.RELEASE_NOTES
