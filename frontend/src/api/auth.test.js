import test from 'node:test'
import assert from 'node:assert/strict'
import { authenticate } from './auth.js'

test('normal authentication makes one request without an extra check', async () => {
  let calls = 0
  const result = await authenticate('/api/auth/login', { email: 'fixture@example.test' },
    { send: async () => { calls += 1; return { id: 1 } }, solve: () => assert.fail('unexpected check') })
  assert.equal(result.id, 1)
  assert.equal(calls, 1)
})
test('account burst requests one check and retries using its proof', async () => {
  const calls = []
  const error = Object.assign(new Error('check'), { status: 429, challenge: { token: 'token', bits: 8 } })
  const result = await authenticate('/api/auth/login', { email: 'fixture@example.test', password: 'fixture' }, {
    send: async (_path, options) => { calls.push(options.body); if (calls.length === 1) throw error; return { id: 1 } },
    solve: async () => '42',
  })
  assert.equal(result.id, 1)
  assert.equal(calls.length, 2)
  assert.equal(calls[1].challenge_token, 'token')
  assert.equal(calls[1].challenge_nonce, '42')
})
test('hard quota remains visible and is never automatically retried', async () => {
  const error = Object.assign(new Error('wait'), { status: 429 })
  let calls = 0
  await assert.rejects(authenticate('/api/auth/login', {}, {
    send: async () => { calls += 1; throw error }, solve: () => assert.fail('unexpected check'),
  }), /wait/)
  assert.equal(calls, 1)
})
test('a failed proof retry cannot create an automatic retry loop', async () => {
  let calls = 0
  const error = Object.assign(new Error('wait'), { status: 429, challenge: { token: 'token', bits: 8 } })
  await assert.rejects(authenticate('/api/auth/login', {}, {
    send: async () => { calls += 1; throw error }, solve: async () => '42',
  }), /wait/)
  assert.equal(calls, 2)
})

test('the API client preserves a server work challenge and its readable message', async t => {
  const { request } = await import('./client.js')
  const challenge = { token: 'a'.repeat(64), bits: 8 }
  t.mock.method(globalThis, 'fetch', async () => ({
    ok: false, status: 429, json: async () => ({ detail: { message: 'Подождите', challenge } }),
  }))
  await assert.rejects(request('/api/auth/login', { method: 'POST', body: { email: 'fixture@example.test' } }),
    error => error.status === 429 && error.message === 'Подождите' && error.challenge.token === challenge.token)
})
