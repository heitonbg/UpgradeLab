const inflight = new Map()
const selected = new Map()
const versions = new Map()
export const REQUIREMENTS_EVENT = 'upgradelab:requirements'
export const latestRequirementsVersion = game => versions.get(game)

// Called after a confirmed game selection, never for search keystrokes.
export async function enrichSelectedGame(game, { send, sleep = ms => new Promise(resolve => setTimeout(resolve, ms)), notify = () => {}, now = Date.now } = {}) {
  if (!game || !send) return null
  if (inflight.has(game)) return inflight.get(game)
  const previous = selected.get(game)
  if (previous && now() - previous.at < 300000) return previous.value
  const promise = (async () => {
    let data = await send('/api/games/requirements', {method:'POST', body:{game}})
    const original = data.version
    for (let attempt=0; attempt<12 && (data.refresh_pending || ['queued','running'].includes(data.status)); attempt++) {
      await sleep(5000)
      data = await send('/api/games/requirements?game='+encodeURIComponent(game))
      if (data.version && data.version !== original) {
        versions.set(game,data.version)
        notify({game,gameId:data.game_id,version:data.version})
        break
      }
    }
    if (data.version) versions.set(game,data.version)
    if (selected.size>=100) selected.delete(selected.keys().next().value)
    selected.set(game,{at:now(),value:data})
    return data
  })().finally(() => inflight.delete(game))
  inflight.set(game,promise)
  return promise
}
