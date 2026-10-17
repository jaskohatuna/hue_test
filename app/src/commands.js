/**
 * One command queue per light. While a request for a light is running, newer
 * changes for that light are merged and sent as one request when it finishes,
 * so dragging a brightness control never floods the Bridge and the last
 * position always wins.
 */
export function createCommandQueue({ send, onResult, onError, onSettled }) {
  const entries = new Map()
  let stopped = false

  function merge(queued, patch) {
    const next = { ...queued, ...patch }
    // A pending brightness change is irrelevant once the light is turned off.
    if (next.on === false) delete next.brightness
    return next
  }

  async function run(id, entry) {
    entry.running = true
    try {
      while (entry.queued && !stopped) {
        const patch = entry.queued
        entry.queued = null
        let result
        try {
          result = await send(id, patch)
        } catch (error) {
          if (stopped) return
          // Changes queued behind a failed command are dropped; the caller resyncs.
          entry.queued = null
          onError(id, error)
          continue
        }
        if (stopped) return
        onResult(id, result)
      }
    } finally {
      entry.running = false
      if (!stopped) {
        if (entries.get(id) === entry && !entry.queued) entries.delete(id)
        onSettled(id)
      }
    }
  }

  return {
    push(id, patch) {
      if (stopped) return
      let entry = entries.get(id)
      if (!entry) {
        entry = { queued: null, running: false }
        entries.set(id, entry)
      }
      entry.queued = merge(entry.queued, patch)
      if (!entry.running) run(id, entry)
    },
    has(id) {
      return entries.has(id)
    },
    get size() {
      return entries.size
    },
    stop() {
      stopped = true
      entries.clear()
    },
  }
}
