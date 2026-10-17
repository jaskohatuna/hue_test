import { computed, ref, watch } from 'vue'
import { Capacitor } from '@capacitor/core'
import { createApi } from './api.js'
import { createCommandQueue } from './commands.js'
import { createBridgeStream, createRefreshQueue } from './live.js'
import { loadServerUrl, normalizeServerUrl, saveServerUrl, webSocketUrl } from './server.js'

const SERVER_CHECK_TIMEOUT = 6000

/**
 * App state: backend address → Bridge setup → lights.
 * Screens: 'boot' | 'server' | 'bridge' | 'settings' | 'lights'.
 */
export function useHue() {
  const screen = ref('boot')
  const serverUrl = ref('')
  const setup = ref(null)
  const checkingServer = ref(false)
  const serverError = ref('')
  const savingSetup = ref(false)
  const setupError = ref('')
  const lights = ref([])
  const loading = ref(false)
  const refreshing = ref(false)
  const error = ref('')
  // Requested state shown until the Bridge confirms it: { [lightId]: { on, brightness } }.
  const optimistic = ref({})
  const activeCommands = ref(0)
  const liveState = ref('connecting')
  const liveDetail = ref('Povezivanje…')
  const configured = computed(() => setup.value?.configured === true)
  const connected = computed(() => setup.value !== null)
  // Light commands are not "busy": each light has its own queue and stays usable.
  const busy = computed(() => checkingServer.value || loading.value || refreshing.value || savingSetup.value)
  const displayLights = computed(() => lights.value.map((light) => {
    const requested = optimistic.value[light.id]
    return requested ? { ...light, ...requested } : light
  }))
  const syncingIds = computed(() => new Set(Object.keys(optimistic.value)))

  let api = null
  let stream = null
  let disposed = false
  let paused = false
  let requestVersion = 0
  let lightRequest = null
  let commands = null
  const liveRefresh = createRefreshQueue({
    canRefresh: () => !disposed && !paused && configured.value && !busy.value && screen.value === 'lights' && !lightRequest && activeCommands.value === 0,
    refresh: () => refreshLights({ background: true }),
  })
  const queueLiveRefresh = liveRefresh.request

  watch([busy, screen, configured, activeCommands], () => {
    liveRefresh.resume()
  })

  function forgetOptimistic(id) {
    const { [id]: _, ...rest } = optimistic.value
    optimistic.value = rest
  }

  /** New queue for the current server/Bridge; late answers of the old one are ignored. */
  function resetCommands() {
    commands?.stop()
    optimistic.value = {}
    activeCommands.value = 0
    const currentApi = api
    commands = createCommandQueue({
      send(id, patch) {
        // A GET that started before this command may show the old state.
        requestVersion += 1
        return currentApi.setLight(id, patch)
      },
      onResult(id, updatedLight) {
        lights.value = lights.value.map((item) => item.id === updatedLight.id ? updatedLight : item)
      },
      onError(id, cause) {
        if (!disposed) error.value = cause.message
      },
      onSettled(id) {
        if (!commands.has(id)) forgetOptimistic(id)
        activeCommands.value = commands.size
        // Other lights may have changed meanwhile; resync once all commands are done.
        queueLiveRefresh()
      },
    })
  }

  function applySetup(nextSetup) {
    const changed = setup.value !== null && (setup.value.bridge_ip !== nextSetup.bridge_ip || setup.value.configured !== nextSetup.configured)
    setup.value = { bridge_ip: nextSetup.bridge_ip, configured: nextSetup.configured }
    if (changed) {
      requestVersion += 1
      resetCommands()
      lights.value = []
      error.value = ''
    }
    if (!nextSetup.configured && screen.value !== 'server') screen.value = 'bridge'
    return changed
  }

  function startStream() {
    if (stream || disposed || paused || !serverUrl.value || !setup.value) return
    stream = createBridgeStream({
      url: webSocketUrl(serverUrl.value),
      onOpen: queueLiveRefresh,
      onStatus(state, detail) {
        liveState.value = state
        liveDetail.value = detail
      },
      onUpdate(update) {
        const changed = applySetup(update)
        liveState.value = update.connected ? 'live' : (update.detail ? 'offline' : 'connecting')
        liveDetail.value = update.connected
          ? 'Prati promjene uživo'
          : (typeof update.detail === 'string' && update.detail ? update.detail : 'Povezivanje…')
        if (update.connected || changed) queueLiveRefresh()
      },
    })
    stream.start()
  }

  function stopStream() {
    stream?.stop()
    stream = null
  }

  async function refreshLights({ background = false } = {}) {
    if (!configured.value || disposed) return

    if (!background) {
      loading.value = lights.value.length === 0
      refreshing.value = true
      error.value = ''
    }

    try {
      if (lightRequest) {
        if (background) {
          queueLiveRefresh()
          return
        }
        try { await lightRequest } catch { /* The active request handles its own error. */ }
      }
      if (!configured.value || disposed) return
      const version = requestVersion
      const currentRequest = api.getLights()
      lightRequest = currentRequest
      try {
        const updatedLights = await currentRequest
        if (!disposed && version === requestVersion) lights.value = updatedLights
      } catch (cause) {
        if (!disposed && version === requestVersion) {
          if (background) {
            liveState.value = 'offline'
            liveDetail.value = cause.message
          } else {
            error.value = cause.message
          }
        }
      } finally {
        if (lightRequest === currentRequest) lightRequest = null
      }
    } finally {
      if (!background) {
        loading.value = false
        refreshing.value = false
      }
      liveRefresh.resume()
    }
  }

  /** Switch to a checked backend; the previous one stays active until here. */
  async function useServer(url, nextApi, nextSetup) {
    stopStream()
    requestVersion += 1
    serverUrl.value = url
    api = nextApi
    resetCommands()
    setup.value = null
    lights.value = []
    error.value = ''
    liveState.value = 'connecting'
    liveDetail.value = 'Povezivanje…'
    screen.value = 'lights'
    applySetup(nextSetup)
    if (configured.value) await refreshLights()
    startStream()
  }

  async function connectServer(input) {
    if (busy.value) return
    serverError.value = ''
    const url = normalizeServerUrl(input)
    if (!url) {
      serverError.value = 'Unesi adresu servera, npr. 192.168.1.20 ili 192.168.1.20:8000.'
      return
    }

    checkingServer.value = true
    try {
      const nextApi = createApi(url)
      const nextSetup = await nextApi.getSetup({ timeout: SERVER_CHECK_TIMEOUT })
      if (disposed) return
      // Not being able to remember the address must not block this session.
      try { await saveServerUrl(url) } catch { /* Asked again on next start. */ }
      checkingServer.value = false
      await useServer(url, nextApi, nextSetup)
    } catch (cause) {
      if (!disposed) serverError.value = cause.message
    } finally {
      checkingServer.value = false
    }
  }

  /** The page itself is served by the backend (browser / iPhone home screen). */
  async function findPageServer() {
    if (Capacitor.isNativePlatform() || !/^https?:$/.test(globalThis.location?.protocol ?? '')) return null
    const pageApi = createApi(location.origin)
    try {
      return { api: pageApi, setup: await pageApi.getSetup({ timeout: SERVER_CHECK_TIMEOUT }) }
    } catch {
      // E.g. the Vite dev server: no Hue backend on this origin.
      return null
    }
  }

  async function boot() {
    const saved = await loadServerUrl()
    if (disposed) return
    if (!saved) {
      const page = await findPageServer()
      if (disposed) return
      if (page) {
        await useServer(location.origin, page.api, page.setup)
        return
      }
      screen.value = 'server'
      return
    }
    serverUrl.value = saved
    await connectServer(saved)
    // Unreachable saved server: show it with the error so it can be retried or changed.
    if (!disposed && !setup.value) screen.value = 'server'
  }

  async function connectBridge({ ip, mode, key }) {
    if (busy.value) return
    setupError.value = ''

    if (!ip) {
      setupError.value = 'Unesi IP adresu svog Hue Bridgea.'
      return
    }
    if (mode === 'key' && !key) {
      setupError.value = 'Unesi postojeći API ključ ili odaberi povezivanje dugmetom.'
      return
    }

    savingSetup.value = true
    requestVersion += 1
    try {
      applySetup(await api.saveSetup(ip, mode === 'key' ? key : null))
      requestVersion += 1
      resetCommands()
      lights.value = []
      screen.value = 'lights'
      await refreshLights()
    } catch (cause) {
      setupError.value = cause.message
    } finally {
      savingSetup.value = false
    }
  }

  /** Show the change at once and send it through the light's queue. */
  function commandLight(light, patch) {
    if (disposed || !commands || !configured.value || light.available === false) return
    error.value = ''
    optimistic.value = { ...optimistic.value, [light.id]: { ...optimistic.value[light.id], ...patch } }
    commands.push(light.id, patch)
    activeCommands.value = commands.size
  }

  function setLightOn(light, on) {
    commandLight(light, { on })
  }

  /** Brightness 1–100; dimming a light that is off turns it on. */
  function setBrightness(light, brightness) {
    if (typeof light.brightness !== 'number') return
    const shown = displayLights.value.find((item) => item.id === light.id) ?? light
    commandLight(light, shown.on ? { brightness } : { on: true, brightness })
  }

  function navigate(next) {
    if (busy.value) return
    if (next === 'server') serverError.value = ''
    if (next === 'bridge') setupError.value = ''
    // Without a Bridge there is no light list to return to.
    screen.value = next === 'lights' && !configured.value ? 'bridge' : next
  }

  /** The OS may freeze background apps: close the socket, reconnect on return. */
  function pause() {
    if (paused || disposed) return
    paused = true
    stopStream()
  }

  function resume() {
    if (!paused || disposed) return
    paused = false
    startStream()
  }

  function dispose() {
    disposed = true
    requestVersion += 1
    commands?.stop()
    liveRefresh.stop()
    stopStream()
  }

  return {
    screen, serverUrl, setup, configured, connected, busy,
    checkingServer, serverError, savingSetup, setupError,
    lights: displayLights, syncingIds, loading, refreshing, error, liveState, liveDetail,
    boot, connectServer, connectBridge, refreshLights, setLightOn, setBrightness, navigate,
    pause, resume, dispose,
  }
}
