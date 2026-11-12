export function marketDataState({loading,error,count}) {
 if(loading)return count?'refreshing':'loading'
 if(error)return count?'partial':'error'
 return count?'success':'empty'
}
export function marketCountLabel(state,count) {
 if(state==='loading')return 'Загружаем объявления…'
 if(state==='refreshing')return 'Обновляем объявления…'
 if(state==='error')return 'Объявления не загружены'
 if(state==='partial')return `По последней загрузке: ${count}. Обновление не удалось.`
 return `Найдено объявлений: ${count}`
}
export function validPriceRange(min,max) {
 const valid=v=>v===''||Number.isFinite(Number(v))&&Number(v)>=0
 return valid(min)&&valid(max)&&(min===''||max===''||Number(min)<=Number(max))
}
