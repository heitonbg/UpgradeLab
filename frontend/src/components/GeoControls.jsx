import { geoWithCity } from '../lib/geoPolicy'
import { CityPicker } from './CityPicker'
export function GeoControls({value,onChange}) {
  const update = patch => onChange({...value,...patch})
  return <fieldset className="price-sources"><legend>Город и получение товара</legend>
    <CityPicker label="Город" value={value.city_id} onChange={city_id=>onChange(geoWithCity(value,city_id))}/>
    <label className="checkbox-label geo-delivery-toggle"><input type="checkbox" checked={value.geo_mode==='delivery'} disabled={!value.city_id} onChange={event=>update({geo_mode:event.target.checked?'delivery':'local'})}/><span>Учитывать доставку в выбранный город<small>Без выбранного города поиск идёт по всем доступным предложениям. С выключенной галочкой — только предложения в выбранном городе.</small></span></label>
    {value.geo_mode==='delivery'&&value.city_id&&<p className="field-hint">Доставка может оплачиваться отдельно. Если её стоимость не указана, итог покупки остаётся неизвестным.</p>}
  </fieldset>
}
