import { request } from './client.js'
import { solveAuthChallenge } from '../lib/authChallenge.js'

export async function authenticate(path, body, { send = request, solve = solveAuthChallenge, onChallenge } = {}) {
  try {
    return await send(path, { method: 'POST', body })
  } catch (error) {
    if (path !== '/api/auth/login' || error.status !== 429 || !error.challenge) throw error
    onChallenge?.()
    const nonce = await solve(error.challenge)
    // Exactly one automatic retry. Hard quotas and subsequent failures remain visible.
    return send(path, { method: 'POST', body: {
      ...body, challenge_token: error.challenge.token, challenge_nonce: nonce,
    } })
  }
}
