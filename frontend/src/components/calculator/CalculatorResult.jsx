import { Button } from '../ui/Button'
import { Card } from '../ui/Card'

export function CalculatorResult({ result, onFind, onSave }) {
  if (!result) return null

  const isCpu = result.bottleneck === 'CPU'
  
  // Если топовое железо — показываем другую карточку
  if (result.is_maxed_out) {
    return (
      <Card className="space-y-4 overflow-hidden">
        <div className="relative h-2 rounded-full bg-gradient-to-r from-green-500 to-emerald-400" />
        
        <div className="flex items-center gap-3">
          <div className="text-4xl">🏆</div>
          <div>
            <h3 className="text-lg font-semibold text-green-400">Ваш ПК топовый!</h3>
            <p className="text-xs text-gray-500">
              {result.cpuName} + {result.gpuName} — система сбалансирована
            </p>
          </div>
        </div>

        <div className="text-2xl font-bold leading-tight">
          Сейчас: ~{result.current_fps} FPS.{' '}
          <span className="text-green-400">После апгрейда: ~{result.upgraded_fps} FPS (+{Math.round(((result.upgraded_fps - result.current_fps) / result.current_fps) * 100)}%)</span>
        </div>

        <div className="bg-green-500/10 border border-green-500/30 rounded-lg p-3">
          <p className="text-sm text-green-300">{result.recommendation}</p>
        </div>

        <div className="text-sm text-gray-400">
          💡 Для максимального FPS попробуйте:
          <ul className="list-disc list-inside mt-2 space-y-1 text-xs">
            <li>Уменьшить настройки графики для роста FPS</li>
            <li>Обновить драйверы видеокарты</li>
            <li>Перейти на монитор с большей частотой обновления</li>
          </ul>
        </div>

        <div className="flex flex-wrap gap-3 pt-2">
          <Button variant="secondary" onClick={onFind}>Найти на бирже</Button>
          <Button variant="secondary" onClick={onSave}>Сохранить сборку</Button>
        </div>
      </Card>
    )
  }

  const title = isCpu ? 'Вас ограничивает: ПРОЦЕССОР' : 'Вас ограничивает: ВИДЕОКАРТА'
  
  const hasSellInfo = result.current_component_price > 0 && result.mode === 'budget_plus_sell'
  const showTotalBudget = hasSellInfo && result.total_budget > 0

  return (
    <Card className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-semibold text-accent">{title}</h3>
        {result.within_budget && (
          <span className="text-xs px-2 py-1 rounded-full bg-accent/20 text-accent font-medium border border-accent/30">
            ✓ В рамках бюджета
          </span>
        )}
      </div>

      {/* Текущий компонент — цена продажи */}
      {result.current_component_price > 0 && (
        <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-md px-3 py-2">
          <p className="text-xs text-yellow-300 font-medium">
            💡 Ваш текущий {isCpu ? 'процессор' : 'видеокарта'} можно продать за{' '}
            <span className="font-bold">{result.current_component_price.toLocaleString('ru-RU')} ₽</span>
          </p>
        </div>
      )}

      {/* Общий бюджет */}
      {showTotalBudget && (
        <div className="bg-accent/10 border border-accent/30 rounded-md px-3 py-2">
          <p className="text-sm text-accent font-medium">
            📊 Ваш бюджет: {result.total_budget.toLocaleString('ru-RU')} ₽
            <span className="text-gray-400 text-xs ml-1">
              ({result.budget?.toLocaleString('ru-RU') ?? '0'} ₽ + {result.current_component_price.toLocaleString('ru-RU')} ₽ от продажи)
            </span>
          </p>
        </div>
      )}

      <div className="text-2xl font-bold leading-tight">
        Сейчас: ~{result.current_fps} FPS.{' '}
        <span className="text-accent">После апгрейда: ~{result.upgraded_fps} FPS</span>
      </div>

      {result.upgrade_component && (
        <div className="text-sm text-gray-300 bg-accent/5 border border-accent/20 rounded-md px-3 py-2">
          <span className="text-accent font-medium">Рекомендуемый апгрейд:</span>{' '}
          {result.upgrade_component}
        </div>
      )}

      {result.ai_warning && (
        <div className={`text-sm rounded-md px-3 py-2 border ${
          result.ai_warning.includes('требуется минимум') || result.ai_warning.includes('ограничения')
            ? 'bg-red-500/10 border-red-500/30 text-red-300'
            : result.ai_warning.includes('подходит')
              ? 'bg-accent/10 border-accent/30 text-accent'
              : 'bg-yellow-500/10 border-yellow-500/30 text-yellow-300'
        }`}>
          <span className="font-medium">⚡ Нейросети:</span> {result.ai_warning}
        </div>
      )}

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
