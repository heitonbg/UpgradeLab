export const cityKey = value => String(value).normalize('NFKC').toLocaleLowerCase('ru-RU').replaceAll('ё','е').trim()
export const cityLabel = city => city.name + ' · ' + city.region
export function citySuggestions(cities,query='') {
  const key=cityKey(query)
  return cities.filter(city=>!key || [city.name,city.region,...(city.aliases||[])].some(value=>cityKey(value).includes(key))).slice(0,30)
}
