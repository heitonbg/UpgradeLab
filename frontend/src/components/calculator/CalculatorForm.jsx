import { useState } from 'react'
import { Button } from '../ui/Button'
import { Select } from '../ui/Select'
import { Modal } from '../ui/Modal'
import { GAMES, MODES } from '../../constants/game'
import { AutoDetectButton } from '../AutoDetectButton'

export function CalculatorForm({ cpus, gpus, rams, onSubmit, loading }) {
  const [cpuId, setCpuId] = useState('')
  const [gpuId, setGpuId] = useState('')
  const [ramId, setRamId] = useState('')
  const [game, setGame] = useState(GAMES[0].value)
  const [mode, setMode] = useState(MODES[0].value) // 1080p Low по умолчанию
  const [budget, setBudget] = useState('')
  const [aiMode, setAiMode] = useState('off') // off, light, heavy
  const [sellMode, setSellMode] = useState('budget_only') // budget_only, budget_plus_sell
  const [manualInput, setManualInput] = useState(false) // Режим ручного ввода
  const [manualCpu, setManualCpu] = useState('')
  const [manualGpu, setManualGpu] = useState('')
  const [showScriptPaste, setShowScriptPaste] = useState(false)
  const [scriptText, setScriptText] = useState('')
  const [scriptError, setScriptError] = useState('')
  const [manualRamGb, setManualRamGb] = useState('16')
  const [manualRamType, setManualRamType] = useState('DDR4')
  const [manualRamChannels, setManualRamChannels] = useState('2')

  // Автоопределение RAM по ручному вводу
  const manualRamMatch = rams.find(r => 
    r.ram_capacity_gb === parseInt(manualRamGb) &&
    r.ram_type === manualRamType &&
    r.ram_channels === parseInt(manualRamChannels)
  )

  const handleAutoDetect = (detectedCpu, detectedGpu) => {
    if (detectedCpu) setCpuId(String(detectedCpu));
    if (detectedGpu) setGpuId(String(detectedGpu));
  };

  const parseScriptOutput = () => {
    setScriptError('')
    try {
      let foundCpu = null
      let foundGpu = null
      let foundRam = null
      let currentSection = null
      let currentModel = ''

      const lines = scriptText.split('\n')
      
      for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim()
        
        // Определяем разделы (=== CPU ===, === Видеокарта ===, и т.д.)
        if (line.match(/^={3,}\s*(CPU|Процессор|Процессор:|Процессор)\s*={3,}$/i)) {
          currentSection = 'cpu'
          currentModel = ''
          continue
        }
        if (line.match(/^={3,}\s*(GPU|Видеокарта|Видеокарта:|Видеокарта)\s*={3,}$/i)) {
          currentSection = 'gpu'
          currentModel = ''
          continue
        }
        if (line.match(/^={3,}\s*(RAM|ОЗУ|Оперативная\s+память|Оперативная\s+память:)\s*={3,}$/i)) {
          currentSection = 'ram'
          currentModel = ''
          continue
        }
        
        // Пропускаем пустые строки и разделители
        if (!line || line.match(/^={3,}$/)) {
          continue
        }
        
        // Парсим в зависимости от текущего раздела
        if (currentSection === 'cpu' && line.match(/^(Модель|Model|CPU|Процессор)\s*:/i)) {
          const cpuName = line.replace(/^(Модель|Model|CPU|Процессор)\s*:/i, '').trim()
          // Убираем лишние символы типа (tm), (r)
          const cleanCpuName = cpuName.replace(/\(tm\)|\(r\)|\*|™|®/gi, '').trim()
          foundCpu = cpus.find(c => 
            c.name.toLowerCase().includes(cleanCpuName.toLowerCase()) ||
            cleanCpuName.toLowerCase().includes(c.name.toLowerCase()) ||
            c.name.toLowerCase().includes(cpuName.toLowerCase())
          )
          // Если не нашли точное совпадение, ищем по базовому названию (без FX, Ryzen и т.д.)
          if (!foundCpu) {
            const baseName = cleanCpuName.replace(/^[A-Z\s]+\s*/i, '').trim()
            foundCpu = cpus.find(c => 
              c.name.toLowerCase().includes(baseName.toLowerCase()) ||
              baseName.toLowerCase().includes(c.name.toLowerCase())
            )
          }
        }
        
        if (currentSection === 'gpu' && line.match(/^(Модель|Model|GPU|Видеокарта)\s*:/i)) {
          const gpuName = line.replace(/^(Модель|Model|GPU|Видеокарта)\s*:/i, '').trim()
          foundGpu = gpus.find(g => 
            g.name.toLowerCase().includes(gpuName.toLowerCase()) ||
            gpuName.toLowerCase().includes(g.name.toLowerCase())
          )
        }
        
        if (currentSection === 'ram' && line.match(/^(Всего|Total|Объём|Объем)\s*:/i)) {
          const ramLine = line.replace(/^(Всего|Total|Объём|Объем)\s*:/i, '').trim()
          // Формат: "7.96 GB" или "7.96 ГБ" или "8 ГБ"
          let ramMatch = ramLine.match(/([\d.]+)\s*(ГБ|GB|GB)\b/i)
          if (ramMatch) {
            const capacity = Math.round(parseFloat(ramMatch[1]))
            // Ищем ближайший объём (с погрешностью ±2 ГБ)
            foundRam = rams.find(r => 
              Math.abs(r.ram_capacity_gb - capacity) <= 2
            )
            // Если не нашли с погрешностью, ищем точное совпадение
            if (!foundRam) {
              foundRam = rams.find(r => r.ram_capacity_gb === capacity)
            }
          }
        }
      }

      if (foundCpu) setCpuId(String(foundCpu.id))
      if (foundGpu) setGpuId(String(foundGpu.id))
      if (foundRam) setRamId(String(foundRam.id))
      
      if (!foundCpu || !foundGpu) {
        let missing = []
        if (!foundCpu) missing.push('CPU')
        if (!foundGpu) missing.push('GPU')
        setScriptError(`Не удалось определить: ${missing.join(', ')}. Проверьте формат данных.`)
        return
      }
      
      setShowScriptPaste(false)
      setScriptText('')
      
      let message = `✅ Определено:\n`
      message += `🔹 CPU: ${foundCpu.name}\n`
      message += `🔹 GPU: ${foundGpu.name}`
      if (foundRam) {
        message += `\n🔹 RAM: ${foundRam.name}`
      }
      alert(message)
    } catch (e) {
      setScriptError('Ошибка парсинга: ' + e.message)
    }
  }

  const canSubmit = (manualInput ? (manualCpu && manualGpu) : (cpuId && gpuId)) && !loading

  return (
    <div className="space-y-5">
      <AutoDetectButton cpus={cpus} gpus={gpus} onDetect={handleAutoDetect} />

      {/* Кнопки загрузки данных */}
      <div className="flex gap-2">
        <a
          href="/scripts/run.bat"
          download="run.bat"
          className="flex-1 px-3 py-2 rounded-md text-xs font-medium bg-card border border-border text-gray-400 hover:text-white hover:border-accent/30 transition text-center"
        >
          📥 Скачать скрипт (Windows)
        </a>
        <button
          onClick={() => setShowScriptPaste(true)}
          className="flex-1 px-3 py-2 rounded-md text-xs font-medium bg-card border border-border text-gray-400 hover:text-white hover:border-accent/30 transition"
        >
          📋 Вставить из скрипта
        </button>
        <button
          onClick={() => {
            setManualInput(!manualInput)
            setScriptText('')
          }}
          className={`flex-1 px-3 py-2 rounded-md text-xs font-medium transition ${
            manualInput
              ? 'bg-accent text-black'
              : 'bg-card border border-border text-gray-400 hover:text-white hover:border-accent/30'
          }`}
        >
          {manualInput ? 'Выбор из списка' : 'Ввести вручную'}
        </button>
      </div>

      {manualInput ? (
        <div className="space-y-4 animate-fade-in">
          <div>
            <label className="block text-sm text-gray-400 mb-2">Процессор (название)</label>
            <input
              type="text"
              value={manualCpu}
              onChange={(e) => setManualCpu(e.target.value)}
              placeholder="Например: AMD Ryzen 5 3600"
              className="w-full bg-card border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Видеокарта (название)</label>
            <input
              type="text"
              value={manualGpu}
              onChange={(e) => setManualGpu(e.target.value)}
              placeholder="Например: NVIDIA GeForce RTX 3060 12GB"
              className="w-full bg-card border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
            />
          </div>
          <p className="text-xs text-gray-500">
            ⚠️ Для точного расчёта лучше выбрать из списка
          </p>
        </div>
      ) : (
        <form
        className="space-y-6"
        onSubmit={(e) => {
          e.preventDefault()
          if (!canSubmit) return
          const b = Number(budget)
          if (manualInput) {
            if (!manualCpu || !manualGpu) {
              alert('Заполните оба поля')
              return
            }
            onSubmit({ 
              manualCpu,
              manualGpu,
              game, 
              mode, 
              budget: b > 0 ? b : null, 
              aiMode,
              sellMode,
            })
          } else {
            onSubmit({ 
              cpuId: Number(cpuId), 
              gpuId: Number(gpuId),
              ramId: ramId || manualRamMatch?.id || null,
              ramManual: !ramId ? {
                type: manualRamType,
                capacity_gb: parseInt(manualRamGb),
                channels: parseInt(manualRamChannels),
              } : null,
              game, 
              mode, 
              budget: b > 0 ? b : null, 
              aiMode,
              sellMode,
            })
          }
        }}
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <Select
            label="Процессор (CPU)"
            value={cpuId}
            onChange={(e) => setCpuId(e.target.value)}
            placeholder="— выберите CPU —"
            options={cpus.map((c) => ({ value: c.id, label: c.name }))}
          />
          <Select
            label="Видеокарта (GPU)"
            value={gpuId}
            onChange={(e) => setGpuId(e.target.value)}
            placeholder="— выберите GPU —"
            options={gpus.map((g) => ({ value: g.id, label: g.name }))}
          />
        </div>

        <Select
          label="Оперативная память (RAM)"
          value={ramId}
          onChange={(e) => setRamId(e.target.value)}
          placeholder="— выберите RAM —"
          options={rams.map((r) => ({ 
            value: r.id, 
            label: `${r.name} (${r.ram_capacity_gb} ГБ ${r.ram_type}, ${r.ram_channels === 2 ? '2ch' : '1ch'})` 
          }))}
        />

        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div>
            <label className="block text-sm text-gray-400 mb-2">Игра</label>
            <select
              value={game}
              onChange={(e) => setGame(e.target.value)}
              className="w-full bg-card border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
            >
              {GAMES.map((g) => (
                <option key={g.value} value={g.value}>{g.label}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-400 mb-2">Режим и разрешение</label>
            <select
              value={mode}
              onChange={(e) => setMode(e.target.value)}
              className="w-full bg-card border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
            >
              {MODES.map((m) => (
                <option key={m.value} value={m.value}>{m.label}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <label className="block text-sm text-gray-400 mb-2">
            Бюджет на апгрейд, ₽ <span className="text-gray-600">(необязательно)</span>
          </label>
          <input
            type="number"
            value={budget}
            onChange={(e) => setBudget(e.target.value)}
            placeholder="Например: 15000"
            min="0"
            step="1000"
            className="w-full max-w-xs bg-card border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
        </div>

        <div>
          <p className="text-sm font-medium text-accent mb-2">ИИ-режим</p>
          <p className="text-xs text-gray-500 mb-2">
            Если планируете запускать нейросети — Stable Diffusion, локальные LLM
          </p>
          <div className="flex flex-wrap gap-3">
            {[
              { value: 'off', label: 'Выкл' },
              { value: 'light', label: 'Лёгкий (SD 1.5, LLM 3B)' },
              { value: 'heavy', label: 'Тяжёлый (SDXL, LLM 7B+)' },
            ].map((opt) => (
              <label key={opt.value} className="flex items-center gap-2 text-xs text-gray-300 cursor-pointer">
                <input
                  type="radio"
                  name="aiMode"
                  value={opt.value}
                  checked={aiMode === opt.value}
                  onChange={(e) => setAiMode(e.target.value)}
                  className="accent-accent"
                />
                {opt.label}
              </label>
            ))}
          </div>
        </div>

        <div>
          <p className="text-sm font-medium text-accent mb-2">Режим расчёта бюджета</p>
          <p className="text-xs text-gray-500 mb-2">
            Хотите продать старый компонент и добавить к бюджету?
          </p>
          <div className="flex flex-col gap-2">
            <label className="flex items-start gap-3 text-xs text-gray-300 cursor-pointer p-2 rounded-md border border-border hover:border-accent/30 transition">
              <input
                type="radio"
                name="sellMode"
                value="budget_only"
                checked={sellMode === 'budget_only'}
                onChange={(e) => setSellMode(e.target.value)}
                className="accent-accent mt-0.5"
              />
              <div>
                <div className="font-medium">Только бюджет</div>
                <div className="text-gray-500 mt-0.5">Ищу апгрейд на {budget ? Number(budget).toLocaleString('ru-RU') + ' ₽' : 'указанный бюджет'}</div>
              </div>
            </label>
            <label className="flex items-start gap-3 text-xs text-gray-300 cursor-pointer p-2 rounded-md border border-border hover:border-accent/30 transition">
              <input
                type="radio"
                name="sellMode"
                value="budget_plus_sell"
                checked={sellMode === 'budget_plus_sell'}
                onChange={(e) => setSellMode(e.target.value)}
                className="accent-accent mt-0.5"
              />
              <div>
                <div className="font-medium">Бюджет + продажа старого</div>
                <div className="text-gray-500 mt-0.5">Продам старый компонент и добавлю к бюджету</div>
              </div>
            </label>
          </div>
        </div>

        <Button type="submit" disabled={!canSubmit}>
          {loading ? 'Расчёт...' : 'Рассчитать узкое место'}
        </Button>
        </form>
      )}

      {/* Модальное окно вставки данных из скрипта */}
      <Modal 
        open={showScriptPaste} 
        onClose={() => { setShowScriptPaste(false); setScriptText(''); setScriptError('') }} 
        title="Вставить данные из скрипта"
        size="lg"
      >
        <div className="space-y-3">
          <div className="bg-blue-500/10 border border-blue-500/30 rounded-md p-3">
            <p className="text-xs text-blue-300 font-medium mb-2">Как запустить на Windows:</p>
            <ol className="text-xs text-gray-400 list-decimal list-inside space-y-1">
              <li>Скачайте <code className="bg-dark px-1 rounded">run.bat</code> выше</li>
              <li>Дважды кликните по <code className="bg-dark px-1 rounded">run.bat</code></li>
              <li>Результат автоматически скопируется в буфер</li>
              <li>Вставьте сюда (Ctrl+V)</li>
            </ol>
          </div>
          <p className="text-xs text-gray-500">
            Или вставьте результат сюда:
          </p>
          <textarea
            value={scriptText}
            onChange={(e) => setScriptText(e.target.value)}
            placeholder="=== CPU ===&#10;Модель: AMD FX-6100&#10;&#10;=== Видеокарта ===&#10;Модель: NVIDIA GTX 1050 Ti&#10;&#10;=== Оперативная память ===&#10;Всего: 8 GB..."
            rows={6}
            className="w-full bg-dark border border-border rounded-md px-3 py-2 text-xs font-mono focus:outline-none focus:ring-2 focus:ring-accent/40"
          />
          {scriptError && <p className="text-xs text-red-400">{scriptError}</p>}
          <div className="flex gap-3">
            <Button onClick={parseScriptOutput} disabled={!scriptText.trim()}>
              Определить комплектующие
            </Button>
            <Button variant="secondary" onClick={() => { setShowScriptPaste(false); setScriptText('') }}>
              Отмена
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  )
}