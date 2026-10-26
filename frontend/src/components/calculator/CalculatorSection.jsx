import { useState } from 'react'
import { calculateUpgrade } from '../../api/calculate'
import { Spinner } from '../ui/Spinner'
import { CalculatorForm } from './CalculatorForm'
import { CalculatorResult } from './CalculatorResult'
import { BottleneckVisualization } from './BottleneckVisualization'
import { AdditionalUpgrades } from './AdditionalUpgrades'

export function CalculatorSection({ cpus, gpus, rams, hardwareLoading, onFindOnMarketplace, onSaveBuild }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleCalculate = async ({ cpuId, gpuId, ramId, ramManual, game, mode, budget, aiMode, sellMode, manualCpu, manualGpu }) => {
    setLoading(true)
    setError(null)
    try {
      // Если ручной ввод — ищем похожие в списке
      let finalCpuId = cpuId
      let finalGpuId = gpuId
      
      if (manualCpu) {
        const found = cpus.find(c => 
          c.name.toLowerCase().includes(manualCpu.toLowerCase()) ||
          manualCpu.toLowerCase().includes(c.name.toLowerCase())
        )
        if (found) finalCpuId = found.id
      }
      
      if (manualGpu) {
        const found = gpus.find(g => 
          g.name.toLowerCase().includes(manualGpu.toLowerCase()) ||
          manualGpu.toLowerCase().includes(g.name.toLowerCase())
        )
        if (found) finalGpuId = found.id
      }
      
      if (!finalCpuId && !manualCpu) {
        setError('Укажите процессор')
        setLoading(false)
        return
      }
      if (!finalGpuId && !manualGpu) {
        setError('Укажите видеокарту')
        setLoading(false)
        return
      }
      if (!finalCpuId || !finalGpuId) {
        setError('Модель не найдена в каталоге. Выберите комплектующие из списка.')
        return
      }

      const payload = {
        cpu_id: finalCpuId,
        gpu_id: finalGpuId,
        ram_id: ramId,
        ram_manual: ramManual,
        game,
        mode,
        budget,
        ai_mode: aiMode,
        sell_mode: sellMode,
      }
      const data = await calculateUpgrade(payload)
      const cpu = cpus.find((c) => c.id === finalCpuId)
      const gpu = gpus.find((g) => g.id === finalGpuId)
      const ram = rams.find((r) => r.id === Number(ramId))
      
      setResult({
        ...data,
        config: payload,
        budget,
        cpuName: cpu?.name ?? manualCpu ?? 'CPU',
        gpuName: gpu?.name ?? manualGpu ?? 'GPU',
        cpuSocket: cpu?.socket,
        ramType: ram?.ram_type ?? ramManual?.type,
        ramCapacity: ram?.ram_capacity_gb ?? ramManual?.capacity_gb,
        game,
        graphicsMode: mode,
      })
    } catch (e) {
      setError(e.message ?? 'Не удалось рассчитать')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  return (
    <section className="space-y-6">
      {hardwareLoading ? (
        <Spinner label="Загружаю комплектующие..." />
      ) : (
        <CalculatorForm
          cpus={cpus}
          gpus={gpus}
          rams={rams}
          loading={loading}
          onSubmit={handleCalculate}
        />
      )}

      {error && (
        <div className="text-sm text-red-400 border border-red-400/30 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      {result && (
        <div className="space-y-6">
          {/* Визуализация bottleneck */}
          <BottleneckVisualization 
            result={result} 
            cpuName={result.cpuName} 
            gpuName={result.gpuName} 
          />
          
          {/* Результат с ценой и апгрейдом */}
          <CalculatorResult
            result={result}
            onFind={onFindOnMarketplace}
            onSave={() => onSaveBuild(result)}
          />
          
          {/* Дополнительные улучшения */}
          <AdditionalUpgrades
            result={result}
            cpuName={result.cpuName}
            gpuName={result.gpuName}
            cpuSocket={result.cpuSocket}
            ramType={result.ramType}
            ramCapacity={result.ramCapacity}
          />
        </div>
      )}
    </section>
  )
}
