import { useState } from 'react'
import { Button } from '../ui/Button'
import { Select } from '../ui/Select'
import { GAMES, MODES } from '../../constants/game'
import { AutoDetectButton } from '../AutoDetectButton'

export function CalculatorForm({ cpus, gpus, onSubmit, loading }) {
  const [cpuId, setCpuId] = useState('')
  const [gpuId, setGpuId] = useState('')
  const [game, setGame] = useState(GAMES[0].value)
  const [mode, setMode] = useState(MODES[0].value) // 1080p Low по умолчанию

  const handleAutoDetect = (detectedCpu, detectedGpu) => {
    if (detectedCpu) setCpuId(String(detectedCpu));
    if (detectedGpu) setGpuId(String(detectedGpu));
  };

  const canSubmit = cpuId && gpuId && !loading

  return (
    <div className="space-y-5">
      <AutoDetectButton cpus={cpus} gpus={gpus} onDetect={handleAutoDetect} />

      <form
        className="space-y-6"
        onSubmit={(e) => {
          e.preventDefault()
          if (!canSubmit) return
          onSubmit({ cpuId: Number(cpuId), gpuId: Number(gpuId), game, mode })
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

        <Button type="submit" disabled={!canSubmit}>
          {loading ? 'Расчёт...' : 'Рассчитать узкое место'}
        </Button>
      </form>
    </div>
  )
}