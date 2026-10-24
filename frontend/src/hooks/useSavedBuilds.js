import { useCallback, useEffect, useState } from 'react'

const STORAGE_KEY = 'pc-upgrade:saved-builds'

function read() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    return raw ? JSON.parse(raw) : []
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
    setBuilds(next)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
  }

  const save = useCallback((build) => {
    const entry = { id: `${Date.now()}`, createdAt: new Date().toISOString(), ...build }
    persist([entry, ...read()])
    return entry
  }, [])

  const clear = useCallback(() => persist([]), [])

  return { builds, save, clear }
}