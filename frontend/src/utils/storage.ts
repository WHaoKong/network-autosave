export interface StorageOptions {
  prefix?: string
  expiry?: number
}

export class Storage {
  private prefix: string
  private defaultExpiry: number

  constructor(options: StorageOptions = {}) {
    this.prefix = options.prefix || 'network-autosave-'
    this.defaultExpiry = options.expiry || 24 * 60 * 60 * 1000
  }

  private getKey(key: string): string {
    return `${this.prefix}${key}`
  }

  setItem<T>(key: string, value: T, expiry?: number): void {
    const storageKey = this.getKey(key)
    const now = Date.now()
    const item = {
      data: value,
      timestamp: now,
      expiry: now + (expiry || this.defaultExpiry)
    }

    try {
      localStorage.setItem(storageKey, JSON.stringify(item))
    } catch (error) {
      console.warn('localStorage write failed:', error)
    }
  }

  getItem<T>(key: string): T | null {
    const storageKey = this.getKey(key)

    try {
      const stored = localStorage.getItem(storageKey)
      if (!stored) return null

      const item = JSON.parse(stored)
      const now = Date.now()

      if (item.expiry && now > item.expiry) {
        this.removeItem(key)
        return null
      }

      return item.data as T
    } catch (error) {
      console.warn('localStorage read failed:', error)
      this.removeItem(key)
      return null
    }
  }

  removeItem(key: string): void {
    const storageKey = this.getKey(key)
    try {
      localStorage.removeItem(storageKey)
    } catch (error) {
      console.warn('localStorage delete failed:', error)
    }
  }

  clear(): void {
    try {
      const keys = Object.keys(localStorage)
      keys.forEach(key => {
        if (key.startsWith(this.prefix)) {
          localStorage.removeItem(key)
        }
      })
    } catch (error) {
      console.warn('localStorage clear failed:', error)
    }
  }

  getAllKeys(): string[] {
    try {
      const keys = Object.keys(localStorage)
      return keys
        .filter(key => key.startsWith(this.prefix))
        .map(key => key.replace(this.prefix, ''))
    } catch (error) {
      console.warn('Failed to list localStorage keys:', error)
      return []
    }
  }

  hasItem(key: string): boolean {
    return this.getItem(key) !== null
  }
}

export const storage = {
  getItem<T>(key: string): T | null {
    const value = localStorage.getItem(key)
    if (!value) return null

    try {
      return JSON.parse(value) as T
    } catch {
      return value as T
    }
  },

  setItem<T>(key: string, value: T): void {
    const stringValue = typeof value === 'string' ? value : JSON.stringify(value)
    localStorage.setItem(key, stringValue)
  },

  removeItem(key: string): void {
    localStorage.removeItem(key)
  },

  clear(): void {
    localStorage.clear()
  }
}

export const appStorage = new Storage({
  prefix: 'network-autosave-v2-',
  expiry: 7 * 24 * 60 * 60 * 1000
})
