const connectionError = 'Server nije dostupan. Provjeri da backend radi i da je telefon na istoj Wi-Fi mreži.'
const timeoutError = 'Server ne odgovara. Provjeri adresu servera i Wi-Fi vezu.'

// Bridge operations take up to 8 s on the backend, pairing up to 15 s + 8 s.
const DEFAULT_TIMEOUT = 12000
const SETUP_TIMEOUT = 30000

async function request(baseUrl, path, { timeout = DEFAULT_TIMEOUT, ...options } = {}) {
  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), timeout)
  let response
  let data

  try {
    try {
      response = await fetch(new URL(path, baseUrl), { ...options, cache: 'no-store', signal: controller.signal })
    } catch {
      throw new Error(controller.signal.aborted ? timeoutError : connectionError)
    }

    try {
      data = await response.json()
    } catch {
      throw new Error(connectionError)
    }
  } finally {
    clearTimeout(timer)
  }

  if (!response.ok) {
    const message = response.status === 422
      ? 'Provjeri IP adresu Bridgea i unesene podatke.'
      : connectionError
    throw new Error(typeof data?.detail === 'string' ? data.detail : message)
  }

  return data
}

function isSetup(data) {
  return typeof data?.bridge_ip === 'string' && typeof data?.configured === 'boolean'
}

export function createApi(baseUrl) {
  return {
    async getSetup({ timeout } = {}) {
      const data = await request(baseUrl, '/api/setup', { timeout })
      // Guards against a different web server answering on this address.
      if (!isSetup(data)) throw new Error('Na ovoj adresi ne radi Hue backend. Provjeri adresu i port.')
      return data
    },

    getLights() {
      return request(baseUrl, '/api/lights')
    },

    saveSetup(bridgeIp, appKey) {
      return request(baseUrl, '/api/setup', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ bridge_ip: bridgeIp, app_key: appKey }),
        timeout: SETUP_TIMEOUT,
      })
    },

    /** `change` is `{ on?: boolean, brightness?: 1–100 }`. */
    setLight(lightId, change) {
      return request(baseUrl, `/api/lights/${encodeURIComponent(lightId)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(change),
      })
    },
  }
}
