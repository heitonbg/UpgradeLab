import test from 'node:test'
import assert from 'node:assert/strict'
import { webcrypto, createHash } from 'node:crypto'
import { solveAuthChallenge } from './authChallenge.js'

test('work check solves the exact server token and bit threshold', async () => {
  const challenge = { token: 'a'.repeat(64), bits: 8 }
  const nonce = await solveAuthChallenge(challenge, { crypto: webcrypto })
  const hash = createHash('sha256').update(`${challenge.token}:${nonce}`).digest()
  assert.equal(hash[0], 0)
  assert.match(nonce, /^\d+$/)
})
test('unsupported difficulty or token is rejected before expensive work', async () => {
  await assert.rejects(solveAuthChallenge({ token: 'bad', bits: 30 }, { crypto: webcrypto }))
})
test('work check has a bounded timeout', async () => {
  let current = 0
  await assert.rejects(solveAuthChallenge({ token: 'a'.repeat(64), bits: 18 },
    { crypto: webcrypto, now: () => current++, maxMs: 0 }), /слишком много времени/)
})
test('browser without WebCrypto gets an actionable message', async () => {
  await assert.rejects(solveAuthChallenge({ token: 'a'.repeat(64), bits: 8 }, { crypto: {} }),
    /Повторите позже/)
})
