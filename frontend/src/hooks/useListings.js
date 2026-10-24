import { useCallback, useEffect, useState } from 'react'
import { createListing, getListings } from '../api/listings'

export function useListings() {
  const [listings, setListings] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  const reload = useCallback(async () => {
    setLoading(true)
    try {
      const data = await getListings()
      setListings(data)
      setError(null)
    } catch (e) {
      setError(e)
    } finally {
      setLoading(false)
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