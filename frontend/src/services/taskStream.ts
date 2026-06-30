import type { Task } from '@/types'

export interface TaskLogEntry {
  timestamp: string
  level: string
  message: string
  task_order?: number
}

export interface TaskStreamSnapshot {
  task: Task | null
  logs: TaskLogEntry[]
}

export interface TaskStreamHandlers {
  onConnected?: (payload: { task_uid?: string; task_order?: number; timestamp?: string }) => void
  onSnapshot?: (payload: TaskStreamSnapshot) => void
  onLog?: (payload: TaskLogEntry) => void
  onStatus?: (payload: Task) => void
  onCompleted?: (payload: { task: Task }) => void
  onError?: (error: Event) => void
}

const buildStreamUrl = (taskUid: string) => {
  const baseUrl = window.location.origin
  return new URL(`/api/task/stream/${encodeURIComponent(taskUid)}`, baseUrl).toString()
}

const parseEventData = <T>(event: MessageEvent<string>): T | null => {
  if (!event.data) {
    return null
  }

  try {
    return JSON.parse(event.data) as T
  } catch {
    return null
  }
}

export const createTaskStream = (taskUid: string, handlers: TaskStreamHandlers) => {
  const eventSource = new EventSource(buildStreamUrl(taskUid), { withCredentials: true })

  eventSource.addEventListener('connected', (event) => {
    const payload = parseEventData<{ task_uid?: string; task_order?: number; timestamp?: string }>(event as MessageEvent<string>)
    if (payload) {
      handlers.onConnected?.(payload)
    }
  })

  eventSource.addEventListener('snapshot', (event) => {
    const payload = parseEventData<TaskStreamSnapshot>(event as MessageEvent<string>)
    if (payload) {
      handlers.onSnapshot?.(payload)
    }
  })

  eventSource.addEventListener('log', (event) => {
    const payload = parseEventData<TaskLogEntry>(event as MessageEvent<string>)
    if (payload) {
      handlers.onLog?.(payload)
    }
  })

  eventSource.addEventListener('status', (event) => {
    const payload = parseEventData<Task>(event as MessageEvent<string>)
    if (payload) {
      handlers.onStatus?.(payload)
    }
  })

  eventSource.addEventListener('completed', (event) => {
    const payload = parseEventData<{ task: Task }>(event as MessageEvent<string>)
    if (payload) {
      handlers.onCompleted?.(payload)
    }
  })

  eventSource.onerror = (error) => {
    handlers.onError?.(error)
  }

  return {
    close: () => eventSource.close()
  }
}
