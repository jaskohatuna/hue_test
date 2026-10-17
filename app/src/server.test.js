import assert from 'node:assert/strict'
import { test } from 'node:test'
import { displayServer, normalizeServerUrl, webSocketUrl } from './server.js'

test('server address accepts IPs and hostnames with or without scheme and port', () => {
  assert.equal(normalizeServerUrl('192.168.1.20'), 'http://192.168.1.20:8000')
  assert.equal(normalizeServerUrl(' 192.168.1.20:8010 '), 'http://192.168.1.20:8010')
  assert.equal(normalizeServerUrl('http://192.168.1.20:8000/'), 'http://192.168.1.20:8000')
  assert.equal(normalizeServerUrl('HTTP://Moj-PC.local'), 'http://moj-pc.local:8000')
  assert.equal(normalizeServerUrl('https://hue.home:8443'), 'https://hue.home:8443')
  assert.equal(normalizeServerUrl('[fd00::5]'), 'http://[fd00::5]:8000')
  assert.equal(normalizeServerUrl('[fd00::5]:9000'), 'http://[fd00::5]:9000')
  // An explicit default port is kept as typed, not replaced by 8000.
  assert.equal(normalizeServerUrl('http://192.168.1.20:80'), 'http://192.168.1.20')
})

test('server address rejects anything that is not a plain origin', () => {
  for (const input of ['', '   ', null, 'ftp://192.168.1.20', 'http://', '192.168.1.20/api', 'http://user:pw@192.168.1.20', '192.168.1.20?x=1', 'a b']) {
    assert.equal(normalizeServerUrl(input), null, String(input))
  }
})

test('websocket and display addresses follow the server address', () => {
  assert.equal(webSocketUrl('http://192.168.1.20:8000'), 'ws://192.168.1.20:8000/api/ws')
  assert.equal(webSocketUrl('https://hue.home:8443'), 'wss://hue.home:8443/api/ws')
  assert.equal(displayServer('http://192.168.1.20:8000'), '192.168.1.20:8000')
  assert.equal(displayServer('https://hue.home:8443'), 'https://hue.home:8443')
})
