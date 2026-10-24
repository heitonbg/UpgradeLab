import { Button } from '../ui/Button'
import { Card } from '../ui/Card'

export function CalculatorResult({ result, onFind, onSave }) {
  if (!result) return null

  const isCpu = result.bottleneck === 'CPU'
  const title = isCpu ? 'Вас ограничивает: ПРОЦЕССОР' : 'Вас ограничивает: ВИДЕОКАРТА'

  return (
    <Card className="space-y-4">
      <h3 className="text-lg font-semibold text-accent">{title}</h3>

      <div className="text-2xl font-bold leading-tight">
        Сейчас: ~{result.current_fps} FPS.{' '}
        <span className="text-accent">После апгрейда: ~{result.upgraded_fps} FPS</span>
      </div>

      <p className="text-sm text-gray-400">{result.recommendation}</p>

      <div className="text-sm">
        Средняя цена на Avito:{' '}
        <span className="text-accent font-medium">{result.avg_price.toLocaleString('ru-RU')} ₽</span>
      </div>

      <div className="flex flex-wrap gap-3 pt-2">
        <Button variant="secondary" onClick={onFind}>Найти на бирже</Button>
        <Button variant="secondary" onClick={onSave}>Сохранить сборку</Button>
      </div>
    </Card>
  )
}