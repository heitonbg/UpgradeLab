import { useState } from 'react'
import { calculateUpgrade } from '../../api/calculate'
import { Spinner } from '../ui/Spinner'
import { CalculatorForm } from './CalculatorForm'
import { CalculatorResult } from './CalculatorResult'

export function CalculatorSection({ cpus, gpus, hardwareLoading, onFindOnMarketplace, onSaveBuild }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const handleCalculate = async ({ cpuId, gpuId, game, mode }) => {
    setLoading(true)
    setError(null)
    try {
      const data = await calculateUpgrade({
        cpu_id: cpuId,
        gpu_id: gpuId,
        game,
        mode,
      })
      const cpu = cpus.find((c) => c.id === cpuId)
      const gpu = gpus.find((g) => g.id === gpuId)
      
      setResult({
        ...data,
        cpuName: cpu?.name ?? '',
        gpuName: gpu?.name ?? '',
        game,
        mode,
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
      <h2 className="text-lg font-medium text-accent">Калькулятор апгрейда</h2>

      {hardwareLoading ? (
        <Spinner label="Загружаю комплектующие..." />
      ) : (
        <CalculatorForm
          cpus={cpus}
          gpus={gpus}
          loading={loading}
          onSubmit={handleCalculate}
        />
      )}

      {error && (
        <div className="text-sm text-red-400 border border-red-400/30 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      <CalculatorResult
        result={result}
        onFind={onFindOnMarketplace}
        onSave={() => onSaveBuild(result)}
      />
    </section>
  )
}