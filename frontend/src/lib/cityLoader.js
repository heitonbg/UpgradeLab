export function validateCities(value) {
 if(!Array.isArray(value)||value.some(c=>!c||typeof c.city_id!=='string'||typeof c.name!=='string'||typeof c.region!=='string'))throw Error('Некорректный ответ справочника городов')
 return value
}
export function createCityLoader(fetcher) {
 let pending=null
 return {load(force=false){
  if(force||!pending){const next=Promise.resolve().then(()=>fetcher('/api/cities')).then(validateCities);pending=next;next.catch(()=>{if(pending===next)pending=null})}
  return pending
 },search(query){return fetcher('/api/cities?q='+encodeURIComponent(query.slice(0,100))).then(validateCities)}}
}
