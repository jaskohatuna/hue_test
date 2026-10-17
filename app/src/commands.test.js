import assert from 'node:assert/strict'
import { test } from 'node:test'
import { createCommandQueue } from './commands.js'

function deferredSender() {
  const calls = []
  return {
    calls,
    send: (id, patch) => new Promise((resolve, reject) => calls.push({ id, patch, resolve, reject })),
  }
}

const flush = () => new Promise((resolve) => setImmediate(resolve))

test('changes during a running command are merged and sent once, last value wins', async () => {
  const sender = deferredSender()
  const results = []
  const settled = []
  const queue = createCommandQueue({
    send: sender.send,
    onResult: (id, result) => results.push([id, result]),
    onError: () => assert.fail('no error expected'),
    onSettled: (id) => settled.push(id),
  })

  queue.push('a', { on: true, brightness: 10 })
  queue.push('a', { brightness: 20 })
  queue.push('a', { brightness: 35 })
  assert.equal(sender.calls.length, 1)
  assert.deepEqual(sender.calls[0].patch, { on: true, brightness: 10 })

  sender.calls[0].resolve('first')
  await flush()
  assert.equal(sender.calls.length, 2)
  assert.deepEqual(sender.calls[1].patch, { brightness: 35 })
  assert.ok(queue.has('a'))

  sender.calls[1].resolve('second')
  await flush()
  assert.deepEqual(results, [['a', 'first'], ['a', 'second']])
  assert.deepEqual(settled, ['a'])
  assert.equal(queue.has('a'), false)
  assert.equal(queue.size, 0)
})

test('lights are independent and turning off drops a queued brightness', async () => {
  const sender = deferredSender()
  const queue = createCommandQueue({ send: sender.send, onResult: () => {}, onError: () => {}, onSettled: () => {} })
  queue.push('a', { brightness: 40 })
  queue.push('b', { on: true })
  assert.deepEqual(sender.calls.map((call) => call.id), ['a', 'b'])
  queue.push('a', { brightness: 60 })
  queue.push('a', { on: false })
  sender.calls[0].resolve()
  await flush()
  assert.deepEqual(sender.calls[2].patch, { on: false })
})

test('a failed command reports once and discards changes queued behind it', async () => {
  const sender = deferredSender()
  const errors = []
  const settled = []
  const queue = createCommandQueue({
    send: sender.send,
    onResult: () => assert.fail('no result expected'),
    onError: (id, error) => errors.push([id, error.message]),
    onSettled: (id) => settled.push(id),
  })
  queue.push('a', { on: true })
  queue.push('a', { brightness: 80 })
  sender.calls[0].reject(new Error('Bridge nije dostupan.'))
  await flush()
  assert.deepEqual(errors, [['a', 'Bridge nije dostupan.']])
  assert.equal(sender.calls.length, 1)
  assert.deepEqual(settled, ['a'])
  assert.equal(queue.has('a'), false)
})

test('stopped queues ignore late results and new commands', async () => {
  const sender = deferredSender()
  const queue = createCommandQueue({
    send: sender.send,
    onResult: () => assert.fail('late result must be ignored'),
    onError: () => assert.fail('late error must be ignored'),
    onSettled: () => assert.fail('stopped queue must not settle'),
  })
  queue.push('a', { on: true })
  queue.stop()
  queue.push('a', { on: false })
  sender.calls[0].resolve('late')
  await flush()
  assert.equal(sender.calls.length, 1)
})
