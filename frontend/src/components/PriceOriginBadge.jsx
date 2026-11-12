import { priceOriginLabel } from '../lib/catalogView'
export function PriceOriginBadge({origin,verifiedAt}){return <span className="price-origin" data-origin={origin||'unknown'}>{priceOriginLabel(origin,verifiedAt)}</span>}
