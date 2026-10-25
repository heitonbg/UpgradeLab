import { Card } from '../ui/Card'

/**
 * Компонент визуализации bottleneck с анимацией
 * Показывает какой компонент ограничивает и как это влияет на FPS
 */
export function BottleneckVisualization({ result, cpuName, gpuName }) {
  const isCpu = result.bottleneck === 'CPU'
  
  return (
    <div className="animate-slide-up">
      <Card className="space-y-4 overflow-hidden">
      {/* Заголовок с градиентом */}
      <div className="relative h-2 rounded-full bg-gradient-to-r from-red-500 via-yellow-500 to-green-500" />
      
      <div className="flex items-center gap-3">
        <div className={`text-4xl ${isCpu ? 'text-red-400' : 'text-blue-400'}`}>
          {isCpu ? '🖥' : '🎮'}
        </div>
        <div>
          <h3 className="text-lg font-semibold text-white">
            Узкое место: <span className={isCpu ? 'text-red-400' : 'text-blue-400'}>
              {isCpu ? 'Процессор' : 'Видеокарта'}
            </span>
          </h3>
          <p className="text-xs text-gray-500">
            {isCpu 
              ? `${cpuName} не раскрывает полностью потенциал видеокарты`
              : `${gpuName} не тянет современные игры на высоких настройках`
            }
          </p>
        </div>
      </div>

      {/* Визуализация FPS */}
      <div className="grid grid-cols-2 gap-4 mt-4">
        <div className="bg-dark/50 rounded-lg p-3 border border-border">
          <p className="text-xs text-gray-500 mb-1">Сейчас</p>
          <p className="text-2xl font-bold text-gray-300">~{result.current_fps}</p>
          <p className="text-xs text-gray-500">FPS</p>
        </div>
        <div className="bg-accent/10 rounded-lg p-3 border border-accent/30">
          <p className="text-xs text-accent/80 mb-1">После апгрейда</p>
          <p className="text-2xl font-bold text-accent">~{result.upgraded_fps}</p>
          <p className="text-xs text-gray-500">FPS</p>
        </div>
      </div>

      {/* Прогресс-бар производительности */}
      <div className="space-y-2">
        <div className="flex justify-between text-xs text-gray-500">
          <span>Текущая производительность</span>
          <span>{Math.round((result.current_fps / result.upgraded_fps) * 100)}%</span>
        </div>
        <div className="h-3 bg-dark rounded-full overflow-hidden border border-border">
          <div 
            className="h-full bg-gradient-to-r from-red-500 to-yellow-500 rounded-full transition-all duration-1000"
            style={{ width: `${Math.round((result.current_fps / result.upgraded_fps) * 100)}%` }}
          />
        </div>
      </div>

      {/* Рекомендация */}
      <div className={`text-sm rounded-lg p-3 border ${
        isCpu 
          ? 'bg-red-500/10 border-red-500/30 text-red-300'
          : 'bg-blue-500/10 border-blue-500/30 text-blue-300'
      }`}>
        {result.recommendation}
      </div>
      </Card>
    </div>
  )
}
