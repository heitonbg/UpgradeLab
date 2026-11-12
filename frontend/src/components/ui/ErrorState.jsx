import { Button } from './Button'
import { Icon } from './Icon'
export function ErrorState({title='Не удалось получить данные',description,onRetry,retrying=false,compact=false}) {
 return <div className={`ui-error-state ${compact?'is-compact':''}`} role="alert"><span className="ui-error-icon"><Icon name="refresh" size={18}/></span><div><h3>{title}</h3>{description&&<p>{description}</p>}{onRetry&&<Button type="button" variant="outline" loading={retrying} onClick={onRetry}>{retrying?'Загружаем…':compact?'Повторить загрузку городов':'Повторить загрузку'}</Button>}</div></div>
}
