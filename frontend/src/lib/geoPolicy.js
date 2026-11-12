export function geoWithCity(current,city_id) {
 return {...current,city_id,geo_mode:!city_id?'all':!current.geo_mode||current.geo_mode==='all'?'local':current.geo_mode}
}
