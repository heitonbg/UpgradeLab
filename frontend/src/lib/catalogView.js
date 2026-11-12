export function sortOffers(offers,mode='price') {
 const number=v=>typeof v==='number'&&Number.isFinite(v)?v:Infinity
 const stamp=v=>Number.isFinite(Date.parse(v))?Date.parse(v):-Infinity
 return [...offers].sort((a,b)=>(mode==='newest'?stamp(b.observed_at)-stamp(a.observed_at):mode==='name'?a.name.localeCompare(b.name,'ru'):number(a.price_rub)-number(b.price_rub))||(a.id||0)-(b.id||0))
}
export function priceOriginLabel(origin,verifiedAt){return origin==='reference'?'Справочная цена':origin==='seller_declared'?'Заявлено продавцом':origin==='catalog_import'?'Цена по прайс-листу':verifiedAt?'Цена сверена по карточке':'Цена не подтверждена'}

export function catalogQuery(q, category, page = 1) {
 return new URLSearchParams({q,...(category?{category}:{}),page:String(page),page_size:'24'}).toString()
}
