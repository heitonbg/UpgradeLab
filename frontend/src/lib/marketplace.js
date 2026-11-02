export const CATEGORIES = [['all','Все комплектующие'],['cpu','Процессоры'],['gpu','Видеокарты'],['motherboard','Материнские платы'],['memory','Оперативная память'],['storage','Накопители'],['psu','Блоки питания'],['case','Корпуса'],['cooler','Охлаждение']]

export function listingCategory(listing) {
  const text = `${listing.title} ${listing.description || ''}`.toLowerCase()
  if (/материнск|motherboard/.test(text)) return 'motherboard'
  if (/блок питан|power supply|\bpsu\b/.test(text)) return 'psu'
  if (/кулер|охлажден|cooler|вентилятор/.test(text)) return 'cooler'
  if (/\bssd\b|\bhdd\b|накопител/.test(text)) return 'storage'
  if (/оперативн|\bram\b|\bddr[345]\b/.test(text)) return 'memory'
  if (/корпус|\bcase\b/.test(text)) return 'case'
  if (/gpu|видеокарт|rtx|gtx|rx\s*\d|geforce|radeon/.test(text)) return 'gpu'
  if (/cpu|процессор|ryzen|core\s*i?[3579]/.test(text)) return 'cpu'
  return 'other'
}

export function listingPrice(listing) {
  const text = String(listing.price ?? '').trim()
  if (!/^\d[\d\s]*(?:[.,]\d{1,2})?\s*(?:₽|руб\.?)?$/i.test(text)) return null
  const price = Number(text.replace(/\s|₽|руб\.?/gi,'').replace(',','.'))
  return Number.isFinite(price) ? price : null
}

export function filterListings(listings, { search='', deal='all', category='all', condition='all', min='', max='', sort='newest' }) {
  const filtered = listings.filter(item => {
    if (search.trim() && !`${item.title} ${item.description || ''}`.toLowerCase().includes(search.trim().toLowerCase())) return false
    const type = item.listing_type || 'sale'
    if (deal !== 'all' && type !== deal) return false
    if (category !== 'all' && listingCategory(item) !== category) return false
    if (condition !== 'all' && (item.condition === 'Новое' ? 'new' : 'used') !== condition) return false
    if (min !== '' || max !== '') {
      const price = listingPrice(item)
      if (type === 'exchange' || price === null) return false
      if (min !== '' && price < Number(min)) return false
      if (max !== '' && price > Number(max)) return false
    }
    return true
  })
  return filtered.sort((a,b) => {
    if (sort === 'price') return (a.listing_type === 'exchange' ? Infinity : listingPrice(a) ?? Infinity) - (b.listing_type === 'exchange' ? Infinity : listingPrice(b) ?? Infinity)
    return (Date.parse(b.created_at) || 0) - (Date.parse(a.created_at) || 0) || b.id-a.id
  })
}
