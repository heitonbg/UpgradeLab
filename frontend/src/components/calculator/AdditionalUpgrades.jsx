import { Card } from '../ui/Card'

/**
 * Блок дополнительных улучшений
 * Показывает что ещё можно улучшить кроме основного bottleneck
 */
export function AdditionalUpgrades({ result, cpuName, gpuName, cpuSocket, ramType, ramCapacity }) {
  const suggestions = []
  
  // Проверка RAM
  if (ramType === 'DDR3') {
    suggestions.push({
      icon: '💾',
      title: 'Замена RAM на DDR4/DDR5',
      desc: 'DDR3 сильно ограничивает современные процессоры. Переход даст +10-20% FPS.',
      priority: 'high',
      color: 'purple',
    })
  } else if (ramCapacity && ramCapacity <= 8) {
    suggestions.push({
      icon: '💾',
      title: 'Увеличение RAM до 16-32 ГБ',
      desc: '8 ГБ мало для современных игр. 16 ГБ — минимум, 32 ГБ — с запасом.',
      priority: 'medium',
      color: 'blue',
    })
  }
  
  if (ramType && ramType !== 'DDR5') {
    suggestions.push({
      icon: '⚡',
      title: 'Переход на DDR5',
      desc: 'DDR5 даёт +8-15% FPS в играх, особенно на AMD Ryzen.',
      priority: 'medium',
      color: 'green',
    })
  }
  
  // Проверка сокета
  if (cpuSocket && cpuSocket !== 'AM5' && cpuSocket !== 'LGA1700') {
    suggestions.push({
      icon: '🔧',
      title: 'Обновление платформы',
      desc: 'Старый сокет ограничивает выбор CPU. Новая материнская плата + новый процессор.',
      priority: 'low',
      color: 'yellow',
    })
  }
  
  // SSD если нет данных
  suggestions.push({
    icon: '💿',
    title: 'SSD NVMe если нет',
    desc: 'SSD значительно ускоряет загрузку игр и снижение stutter.',
    priority: 'low',
    color: 'cyan',
  })
  
  // Блок питания
  suggestions.push({
    icon: '🔌',
    title: 'Проверка блока питания',
    desc: 'Для нового GPU нужен качественный БП 650W+ (80+ Gold).',
    priority: 'low',
    color: 'orange',
  })
  
  if (suggestions.length === 0) return null
  
  return (
    <div className="animate-slide-up">
      <Card className="space-y-3">
      <div className="flex items-center gap-2">
        <span className="text-2xl">🚀</span>
        <h3 className="text-lg font-semibold text-white">Дополнительные улучшения</h3>
      </div>
      
      <div className="space-y-2">
        {suggestions.map((item, idx) => (
          <div 
            key={idx}
            className={`flex items-start gap-3 p-3 rounded-lg border transition-all hover:scale-[1.02] ${
              item.priority === 'high' 
                ? 'bg-purple-500/10 border-purple-500/30'
                : item.priority === 'medium'
                  ? 'bg-blue-500/10 border-blue-500/30'
                  : 'bg-gray-500/10 border-gray-500/30'
            }`}
          >
            <span className="text-2xl">{item.icon}</span>
            <div className="flex-1">
              <div className="flex items-center gap-2">
                <p className="text-sm font-medium text-white">{item.title}</p>
                {item.priority === 'high' && (
                  <span className="text-[10px] px-1.5 py-0.5 rounded bg-purple-500/30 text-purple-300">
                    Важно
                  </span>
                )}
              </div>
              <p className="text-xs text-gray-400 mt-1">{item.desc}</p>
            </div>
          </div>
        ))}
      </div>
    </Card>
    </div>
  )
}
