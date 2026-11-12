import { CategoryImage } from '../CategoryImage'
import { deliveryText } from '../../lib/listingDetails'
import { ListingPhoto } from './ListingPhoto'
import { Icon } from '../ui/Icon'
import { CATEGORIES, listingCategory, listingPrice } from '../../lib/marketplace'
export function ListingCard({listing}) {
 const category=listingCategory(listing),label=CATEGORIES.find(([key])=>key===category)?.[1]||'Комплектующее'
 const price=listingPrice(listing),exchange=listing.listing_type==='exchange'
 const date=new Date(listing.created_at).toLocaleDateString('ru-RU',{day:'numeric',month:'short'})
 const availability=listing.availability_confirmed_at?`${listing.seller_availability==='expired'?'Заявление устарело':'Наличие заявлено'} · ${new Date(listing.availability_confirmed_at).toLocaleDateString('ru-RU')}`:'Наличие продавцом не подтверждено'
 return <article className="listing-tile"><div className={`listing-media ${listing.photo_url?'has-photo':''}`}>{listing.photo_url?<ListingPhoto src={listing.photo_url} alt={listing.title}/>:<CategoryImage category={listing.category} label/>}<span className={`listing-deal ${exchange?'is-exchange':''}`}>{exchange?'Обмен':'Продажа'}</span></div>
 <div className="listing-tile-body"><div className="listing-meta"><span>{label}</span><span className="condition-badge">{listing.condition}</span></div><h3>{listing.title}</h3><p className="listing-value">{exchange?'Обмен':price!==null?`${price.toLocaleString('ru-RU')} ₽`:listing.price}</p><p className="listing-location">{listing.city_label||'Город не указан'}</p><p className="field-hint">{deliveryText(listing.delivery)}</p><p className="listing-excerpt">{exchange?'На: '+listing.exchange_for:listing.description||'Состояние и подробности — в объявлении.'}</p>{listing.technical_assessment?.state==='contradictory'&&<p className="field-hint">В характеристиках есть противоречия — проверьте перед покупкой.</p>}<p className="field-hint listing-availability">{availability}</p><div className="listing-tile-foot"><span>{listing.seller_name||date}</span><span>Подробнее<Icon name="arrow" size={15}/></span></div></div></article>
}
