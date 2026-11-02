import { ListingCard } from './ListingCard'
import { LoadingPanel } from '../ui/LoadingPanel'
import { Icon } from '../ui/Icon'
import { Button } from '../ui/Button'

export function ListingGrid({ listings, loading, onClick, emptyMessage, hasFilters, onReset, onCreate }) {
  if(loading)return <LoadingPanel title="Загружаем объявления" cards/>
  if(!listings?.length)return <div className="market-empty"><span className="empty-icon"><Icon name={hasFilters?'search':'box'} size={36}/></span><p className="eyebrow">{hasFilters?'Уточним поиск':'Биржа UpgradeLab'}</p><h3>{hasFilters?'По этим условиям ничего не нашлось':'Здесь появится ваш следующий апгрейд'}</h3><p>{emptyMessage||(hasFilters?'Попробуйте другое название или уберите часть фильтров.':'Пока объявлений нет. Вы можете первым предложить комплектующую на продажу или обмен.')}</p>{hasFilters?<Button type="button" variant="secondary" onClick={onReset}>Сбросить фильтры</Button>:<Button type="button" onClick={onCreate}><Icon name="plus" size={16}/>Разместить объявление</Button>}</div>
  return <div className="market-grid result-reveal">{listings.map(listing=><button key={listing.id} type="button" onClick={()=>onClick?.(listing)} className="listing-open" aria-label={`Открыть объявление: ${listing.title}`}><ListingCard listing={listing}/></button>)}</div>
}
