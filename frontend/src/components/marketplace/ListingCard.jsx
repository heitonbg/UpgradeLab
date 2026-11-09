import { ListingPhoto } from './ListingPhoto'
import { Icon } from '../ui/Icon'
import { CATEGORIES, listingCategory, listingPrice } from '../../lib/marketplace'

export function ListingCard({ listing }) {
  const category=listingCategory(listing)
  const label=CATEGORIES.find(([key])=>key===category)?.[1]||'Комплектующее'
  const icon={cpu:'chip',gpu:'gpu',storage:'drive',psu:'shield',cooler:'fan'}[category]||'box'
  const price=listingPrice(listing)
  const exchange=listing.listing_type==='exchange'
  const date=new Date(listing.created_at).toLocaleDateString('ru-RU',{day:'numeric',month:'short'})
  return <article className="listing-tile">
    <div className={`listing-media ${listing.photo_url?'has-photo':''}`}>{listing.photo_url?<ListingPhoto src={listing.photo_url} alt={listing.title}/>:<Icon name={icon} size={60}/>}<span className={`listing-deal ${exchange?'is-exchange':''}`}>{exchange?'Обмен':'Продажа'}</span></div>
    <div className="listing-tile-body"><div className="listing-meta"><span>{label}</span><span className="condition-badge">{listing.condition}</span></div><h3>{listing.title}</h3><p className="field-hint">{listing.city_label||"Город не указан"}</p><p className="listing-value">{exchange?'Обмен':price!==null?`${price.toLocaleString('ru-RU')} ₽`:listing.price}</p>{exchange?<p className="listing-excerpt">На: {listing.exchange_for}</p>:<p className="listing-excerpt">{listing.description||'Описание и контакты — в объявлении.'}</p>}<div className="listing-tile-foot"><span>{date}</span><span>Смотреть<Icon name="arrow" size={15}/></span></div></div>
  </article>
}
