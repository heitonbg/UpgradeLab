import test from 'node:test'
import assert from 'node:assert/strict'
import { runSearch } from './searchJobs.js'
import { ApiError } from './client.js'

function memoryStorage() {
  const values = new Map()
  return { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value),
    removeItem: key => values.delete(key) }
}
const payload = { budget: 50000 }
const sleep = async () => {}

test('a polling connection failure does not start another search', async () => {
  const calls = []
  const responses = [{ id: 'job', status: 'queued' }, new Error('connection closed'),
    { id: 'job', status: 'running' }, { id: 'job', status: 'completed', result: { total_price: 48000 } }]
  const result = await runSearch('assemble', payload, { storage: memoryStorage(), sleep,
    send: async (path, options) => { calls.push([path, options]); const next = responses.shift();
      if (next instanceof Error) throw next; return next } })
  assert.equal(result.total_price, 48000)
  assert.equal(calls.filter(([, options]) => options.method === 'POST').length, 1)
})

test('a lost POST response retries with the same idempotency token', async () => {
  const tokens = []
  const result = await runSearch('assemble', payload, { storage: memoryStorage(), sleep,
    send: async (path, options) => {
      if (options.method === 'POST') {
        tokens.push(options.body.client_request_id)
        if (tokens.length === 1) throw new ApiError(503, 'unavailable')
        return { id: 'job', status: 'queued' }
      }
      return { id: 'job', status: 'completed', result: { ok: true } }
    } })
  assert.equal(result.ok, true)
  assert.equal(tokens.length, 2)
  assert.equal(tokens[0], tokens[1])
})

test('returning to the same search resumes a saved job without another POST', async () => {
  const storage = memoryStorage()
  storage.setItem('upgradelab:search:assemble', JSON.stringify({ signature: JSON.stringify(payload), requestId: 'old', id: 'saved' }))
  const result = await runSearch('assemble', payload, { storage, sleep, send: async (path, options) => {
    assert.equal(path, '/api/search-jobs/saved');assert.notEqual(options.method, 'POST')
    return { id: 'saved', status: 'completed', result: { status: 'draft' } }
  } })
  assert.equal(result.status, 'draft')
  assert.equal(storage.getItem('upgradelab:search:assemble'), null)
})

test('server failure is reported and does not keep polling indefinitely', async () => {
  const storage = memoryStorage()
  await assert.rejects(runSearch('calculate', payload, { storage, sleep,
    send: async () => ({ id: 'job', status: 'failed', error: 'Backend перезапустился' }) }), /перезапустился/)
  assert.equal(storage.getItem('upgradelab:search:calculate'), null)
})

test('an unavailable backend keeps the job reference for a later retry', async () => {
  const storage = memoryStorage()
  await assert.rejects(runSearch('assemble', payload, { storage, sleep,
    send: async () => { throw new ApiError(503, 'offline') } }), /недоступен/)
  assert.ok(storage.getItem('upgradelab:search:assemble'))
})
