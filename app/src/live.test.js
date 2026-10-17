import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createBridgeStream, createRefreshQueue } from './live.js'

function fakeSocketClass() {
  return class FakeSocket {
    static instances = []
    constructor(url) {
      this.url = url
      this.closed = false
      this.constructor.instances.push(this)
    }
    close() {
      this.closed = true
      this.onclose?.()
    }
    open() { this.onopen?.() }
    message(data) { this.onmessage?.({ data }) }
  }
}

test('stream connects to the server URL, validates messages and cleans up its socket', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const Socket = fakeSocketClass()
  const updates = []
  let opens = 0
  const stream = createBridgeStream({
    socketClass: Socket,
    url: 'wss://home.test:8000/api/ws',
    onUpdate: (update) => updates.push(update),
    onStatus: () => {},
    onOpen: () => { opens += 1 },
  })
  stream.start()
  stream.start()
  assert.equal(Socket.instances.length, 1)
  const socket = Socket.instances[0]
  assert.equal(socket.url, 'wss://home.test:8000/api/ws')
  socket.open()
  socket.message('invalid JSON')
  socket.message(JSON.stringify({ type: 'other' }))
  socket.message(JSON.stringify({ type: 'bridge_update', connected: true, configured: true, bridge_ip: '192.168.1.10', detail: '' }))
  assert.equal(opens, 1)
  assert.equal(updates.length, 1)
  stream.stop()
  assert.equal(socket.closed, true)
  assert.equal(socket.onmessage, null)
  t.mock.timers.tick(30000)
  assert.equal(Socket.instances.length, 1)
})

test('stream reconnects with capped backoff, refreshes on reopen and cancels retries', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const Socket = fakeSocketClass()
  const states = []
  let opens = 0
  const stream = createBridgeStream({
    socketClass: Socket,
    url: 'ws://192.168.1.20:8000/api/ws',
    onUpdate: () => {},
    onStatus: (state) => states.push(state),
    onOpen: () => { opens += 1 },
  })
  stream.start()
  assert.equal(Socket.instances[0].url, 'ws://192.168.1.20:8000/api/ws')
  for (const delay of [1000, 2000, 4000, 8000, 15000, 15000]) {
    const count = Socket.instances.length
    Socket.instances.at(-1).close()
    t.mock.timers.tick(delay - 1)
    assert.equal(Socket.instances.length, count)
    t.mock.timers.tick(1)
    assert.equal(Socket.instances.length, count + 1)
  }
  Socket.instances.at(-1).open()
  assert.equal(opens, 1)
  Socket.instances.at(-1).close()
  const count = Socket.instances.length
  stream.stop()
  t.mock.timers.tick(30000)
  assert.equal(Socket.instances.length, count)
  assert.ok(states.includes('offline'))
})

test('unsupported WebSocket reports a fallback without blocking HTTP', () => {
  const states = []
  const stream = createBridgeStream({ socketClass: null, onUpdate: () => {}, onOpen: () => {}, onStatus: (state) => states.push(state) })
  stream.start()
  assert.deepEqual(states, ['unsupported'])
  stream.stop()
})

test('refresh queue coalesces events, defers while busy and never overlaps GETs', async (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  let allowed = false
  let count = 0
  let finish
  const queue = createRefreshQueue({
    canRefresh: () => allowed,
    refresh: () => {
      count += 1
      return new Promise((resolve) => { finish = resolve })
    },
  })
  queue.request()
  queue.request()
  queue.request()
  t.mock.timers.tick(125)
  assert.equal(count, 0)
  allowed = true
  queue.resume()
  t.mock.timers.tick(125)
  assert.equal(count, 1)
  queue.request()
  queue.request()
  t.mock.timers.tick(1000)
  assert.equal(count, 1)
  finish()
  await Promise.resolve()
  t.mock.timers.tick(125)
  assert.equal(count, 2)
  finish()
  await Promise.resolve()
  queue.request()
  queue.stop()
  t.mock.timers.tick(1000)
  assert.equal(count, 2)
})

test('stream can be paused and resumed, opening a fresh socket each time', (t) => {
  t.mock.timers.enable({ apis: ['setTimeout'] })
  const Socket = fakeSocketClass()
  let opens = 0
  const stream = createBridgeStream({
    socketClass: Socket,
    url: 'ws://192.168.1.20:8000/api/ws',
    onUpdate: () => {},
    onStatus: () => {},
    onOpen: () => { opens += 1 },
  })
  stream.start()
  Socket.instances[0].close()
  t.mock.timers.tick(1000)
  Socket.instances[1].close()
  stream.stop()
  stream.start()
  assert.equal(Socket.instances.length, 3)
  Socket.instances[2].open()
  assert.equal(opens, 1)
  // The backoff restarts after a resume instead of continuing from 2 s.
  Socket.instances[2].close()
  t.mock.timers.tick(1000)
  assert.equal(Socket.instances.length, 4)
  stream.stop()
})
