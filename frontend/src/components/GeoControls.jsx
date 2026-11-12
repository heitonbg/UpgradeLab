import { geoWithCity } from '../lib/geoPolicy'
import { Select } from './ui/Select'
import { CityPicker } from './CityPicker'
export function GeoControls({value,onChange}) {
  const update = patch => onChange({...value,...patch})
  return <fieldset className="price-sources"><legend>Город и получение товара</legend>
    <CityPicker value={value.city_id} required={value.geo_mode!=='all'} onChange={city_id=>onChange(geoWithCity(value,city_id))}/>
    <div className="form-grid"><label>Где искать<Select value={value.geo_mode||'all'} onChange={e=>update({geo_mode:e.target.value})}>
      <option value="all">Все города</option><option value="local">В выбранном городе</option><option value="delivery">В городе и с доставкой</option>
    </Select></label><label>Цена одной детали до, ₽<input type="number" min="1" max="100000000" value={value.max_price??''} onChange={e=>update({max_price:e.target.value?Number(e.target.value):null})}/></label></div>
    {value.geo_mode!=='all'&&!value.city_id&&<p role="alert" className="field-hint">Выберите город из справочника.</p>}
    <p className="field-hint">Город продавца — его заявление. Неизвестные наличие и доставка не считаются подтверждёнными. Неизвестная доставка не считается бесплатной.</p>
  </fieldset>
}
