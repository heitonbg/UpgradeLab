// A short, one-use work check is requested only during a burst for one account.
export async function solveAuthChallenge(challenge, { crypto = globalThis.crypto, now = Date.now, maxMs = 45000 } = {}) {
  if (!crypto?.subtle || !/^[a-f0-9]{64}$/.test(challenge?.token || '') ||
      !Number.isInteger(challenge?.bits) || challenge.bits < 8 || challenge.bits > 22) {
    throw new Error('Не удалось проверить запрос входа. Повторите позже.')
  }
  const started = now()
  const encoder = new TextEncoder()
  const matches = buffer => {
    const bytes = new Uint8Array(buffer)
    const whole = Math.floor(challenge.bits / 8)
    for (let index = 0; index < whole; index += 1) if (bytes[index] !== 0) return false
    const remainder = challenge.bits % 8
    return !remainder || (bytes[whole] >> (8 - remainder)) === 0
  }
  for (let first = 0; first < 2 ** (challenge.bits + 4); first += 256) {
    if (now() - started >= maxMs) break
    const checks = await Promise.all(Array.from({ length: 256 }, (_, offset) =>
      crypto.subtle.digest('SHA-256', encoder.encode(`${challenge.token}:${first + offset}`))))
    const index = checks.findIndex(matches)
    if (index !== -1) return String(first + index)
    if (first % 4096 === 0) await new Promise(resolve => setTimeout(resolve, 0))
  }
  throw new Error('Проверка входа заняла слишком много времени. Повторите позже.')
}
