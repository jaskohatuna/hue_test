import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createApi } from './api.js'

function captureFetch(t, body = { id: 'a', name: 'Lampa', on: true, brightness: 40 }) {
  const calls = []
  t.mock.method(globalThis, 'fetch', async (url, options) => {
    calls.push({ url: String(url), options })
    return { ok: true, status: 200, json: async () => body }
  })
  return calls
}

test('light commands send exactly the requested change as the body', async (t) => {
  const calls = captureFetch(t)
  const api = createApi('http://192.168.1.20:8000')
  await api.setLight('a b', { on: true, brightness: 40 })
  await api.setLight('a', { on: false })
  assert.equal(calls[0].url, 'http://192.168.1.20:8000/api/lights/a%20b')
  assert.equal(calls[0].options.method, 'PUT')
  assert.deepEqual(JSON.parse(calls[0].options.body), { on: true, brightness: 40 })
  assert.deepEqual(JSON.parse(calls[1].options.body), { on: false })
})

test('server errors show the backend message', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => ({ ok: false, status: 503, json: async () => ({ detail: 'Bridge nije dostupan.' }) }))
  await assert.rejects(createApi('http://pc:8000').getLights(), { message: 'Bridge nije dostupan.' })
})
