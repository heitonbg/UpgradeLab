import { publicSourceIds } from './publicSources.js'

const DEFAULT_GEO = { city_id: null, geo_mode: 'all', max_price: null }

export function storeSearchDefaults(sources, geo) {
  const value = geo?.geo && typeof geo.geo === 'object' ? geo.geo : geo
  return {
    sources: publicSourceIds(sources),
    geo: {
      city_id: value?.city_id ?? DEFAULT_GEO.city_id,
      geo_mode: value?.geo_mode ?? DEFAULT_GEO.geo_mode,
      max_price: value?.max_price ?? DEFAULT_GEO.max_price,
    },
  }
}
