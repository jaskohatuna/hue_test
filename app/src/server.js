import { Preferences } from '@capacitor/preferences'

const STORAGE_KEY = 'server-url'
export const DEFAULT_PORT = '8000'

/**
 * Turn user input such as "192.168.1.20", "pc.local:8000" or
 * "http://192.168.1.20:8000/" into an origin like "http://192.168.1.20:8000".
 * Returns null when the input is not a usable server address.
 */
export function normalizeServerUrl(input) {
  const text = String(input ?? '').trim()
  if (!text) return null
  const withScheme = /^[a-z][a-z0-9+.-]*:\/\//i.test(text) ? text : `http://${text}`

  let url
  try {
    url = new URL(withScheme)
  } catch {
    return null
  }
  if (url.protocol !== 'http:' && url.protocol !== 'https:') return null
  if (!url.hostname || url.username || url.password || url.search || url.hash) return null
  if (url.pathname !== '/' && url.pathname !== '') return null

  // The backend listens on 8000 unless the user typed a port explicitly.
  const hasPort = /^[a-z]+:\/\/(\[[^\]]+\]|[^/:]+):\d+/i.test(withScheme)
  if (!hasPort) url.port = DEFAULT_PORT
  return url.origin
}

export function webSocketUrl(serverUrl) {
  const url = new URL('/api/ws', serverUrl)
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:'
  return url.href
}

/** Short form for display, e.g. "192.168.1.20:8000". */
export function displayServer(serverUrl) {
  return serverUrl ? serverUrl.replace(/^http:\/\//, '') : ''
}

// Preferences uses native storage in the app and localStorage in Chrome.
export async function loadServerUrl() {
  try {
    const { value } = await Preferences.get({ key: STORAGE_KEY })
    return normalizeServerUrl(value)
  } catch {
    return null
  }
}

export async function saveServerUrl(serverUrl) {
  await Preferences.set({ key: STORAGE_KEY, value: serverUrl })
}
