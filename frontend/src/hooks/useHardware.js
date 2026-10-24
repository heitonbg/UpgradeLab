import { useEffect, useState } from 'react'
import { getHardware } from '../api/hardware'

export function useHardware() {
  const [cpus, setCpus] = useState([])
  const [gpus, setGpus] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    let alive = true
    setLoading(true)
    getHardware()
      .then((data) => {
        if (!alive) return
        setCpus(data.filter((h) => h.type === 'CPU'))
        setGpus(data.filter((h) => h.type === 'GPU'))
        setError(null)
      })
      .catch((e) => alive && setError(e))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [])

  return { cpus, gpus, loading, error }
}