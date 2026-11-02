import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'pc-upgrade:saved-builds'

function read() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    const data = raw ? JSON.parse(raw) : []
    return Array.isArray(data) ? data.filter(b=>b&&typeof b==='object'&&b.config) : []
  } catch {
    return []
  }
}

export function useSavedBuilds() {
  const [builds, setBuilds] = useState(read)

  useEffect(() => {
    const onStorage = (e) => {
      if (e.key === STORAGE_KEY) setBuilds(read())
    }
    window.addEventListener('storage', onStorage)
    return () => window.removeEventListener('storage', onStorage)
  }, [])

  const persist = (next) => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    setBuilds(next)
  }

  const save = useCallback((build) => {
    const entry = { ...build, id: crypto.randomUUID(), createdAt: new Date().toISOString() }
    persist([entry, ...read()])
    return entry
  }, [])

  const clear = useCallback(() => persist([]), [])
  const remove = useCallback(id=>persist(read().filter(build=>build.id!==id)), [])

  return { builds, save, clear, remove }
}
