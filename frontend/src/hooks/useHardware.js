import { useEffect, useState } from 'react'
import { getHardware } from '../api/hardware'

export function useHardware(enabled = true) {
  const [cpus, setCpus] = useState([])
  const [gpus, setGpus] = useState([])
  const [rams, setRams] = useState([])
  const [loading, setLoading] = useState(enabled)
  const [error, setError] = useState(null)

  useEffect(() => {
    if (!enabled) return
    let alive = true
    setLoading(true)
    getHardware()
      .then((data) => {
        if (!alive) return
        setCpus(data.filter((h) => h.type === 'CPU'))
        setGpus(data.filter((h) => h.type === 'GPU'))
        setRams(data.filter((h) => h.type === 'RAM'))
        setError(null)
      })
      .catch((e) => alive && setError(e))
      .finally(() => alive && setLoading(false))
    return () => { alive = false }
  }, [enabled])

  return { cpus, gpus, rams, loading, error }
}
