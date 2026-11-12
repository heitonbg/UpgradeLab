import { useCallback, useEffect, useRef, useState } from 'react'
import { createListing, getListings } from '../api/listings'

export function useListings() {
  const [listings, setListings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const sequence=useRef(0)
  const reload = useCallback(async () => {
    const current=++sequence.current
    setLoading(true)
    try {
      const data = await getListings()
      if(!Array.isArray(data))throw Error('Некорректный ответ списка объявлений')
      if(current!==sequence.current)return
      setListings(data)
      setError(null)
    } catch (e) {
      if(current===sequence.current)setError(e)
    } finally {
      if(current===sequence.current)setLoading(false)
    }
  }, [])

  useEffect(() => { reload() }, [reload])

  const add = useCallback(async (payload) => {
    const created = await createListing(payload)
    setListings((prev) => [created, ...prev])
    return created
  }, [])

  return { listings, loading, error, reload, add }
}