export function createRefreshQueue({ canRefresh, refresh }) {
  let pending = false
  let running = false
  let timer = null
  let stopped = false

  function schedule() {
    if (stopped || !pending || running || timer !== null) return
    timer = setTimeout(async () => {
      timer = null
      if (stopped || !pending || !canRefresh()) return
      pending = false
      running = true
      try {
        await refresh()
      } finally {
        running = false
        schedule()
      }
    }, 125)
  }

  return {
    request() {
      if (stopped) return
      pending = true
      schedule()
    },
    resume: schedule,
    stop() {
      stopped = true
      pending = false
      clearTimeout(timer)
      timer = null
    },
  }
}

/**
 * WebSocket to the backend's /api/ws. It can be stopped while the app is in
 * the background and started again on resume; every (re)open triggers onOpen.
 */
export function createBridgeStream({ url, onUpdate, onStatus, onOpen, socketClass = globalThis.WebSocket }) {
  let socket = null
  let retryTimer = null
  let retryDelay = 1000
  let stopped = true

  function retry() {
    if (stopped || retryTimer !== null) return
    onStatus('offline', 'Veza prekinuta. Ponovno povezivanje…')
    retryTimer = setTimeout(() => {
      retryTimer = null
      connect()
    }, retryDelay)
    retryDelay = Math.min(retryDelay * 2, 15000)
  }

  function connect() {
    if (stopped) return
    onStatus('connecting', 'Povezivanje…')

    let current
    try {
      current = new socketClass(url)
      socket = current
    } catch {
      retry()
      return
    }

    current.onopen = () => {
      if (stopped || socket !== current) return
      retryDelay = 1000
      onOpen()
    }
    current.onmessage = (event) => {
      if (stopped || socket !== current) return
      let update
      try {
        update = JSON.parse(event.data)
      } catch {
        return
      }
      if (update?.type !== 'bridge_update' || typeof update.connected !== 'boolean' || typeof update.configured !== 'boolean' || typeof update.bridge_ip !== 'string') return
      onUpdate(update)
    }
    current.onerror = () => {
      if (stopped || socket !== current) return
      current.close()
    }
    current.onclose = () => {
      if (stopped || socket !== current) return
      socket = null
      retry()
    }
  }

  return {
    start() {
      if (!stopped) return
      stopped = false
      retryDelay = 1000
      if (!socketClass) {
        onStatus('unsupported', 'Praćenje uživo nije dostupno. Koristi Osvježi.')
        return
      }
      connect()
    },
    stop() {
      stopped = true
      clearTimeout(retryTimer)
      retryTimer = null
      if (socket) {
        const current = socket
        socket = null
        current.onopen = null
        current.onmessage = null
        current.onerror = null
        current.onclose = null
        current.close()
      }
    },
  }
}
