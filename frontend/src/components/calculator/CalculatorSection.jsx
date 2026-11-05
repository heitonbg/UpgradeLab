import { useState } from 'react'
import { calculateUpgrade } from '../../api/calculate'
import { Spinner } from '../ui/Spinner'
import { CalculatorForm } from './CalculatorForm'
import { CalculatorResult } from './CalculatorResult'
import { BottleneckVisualization } from './BottleneckVisualization'
import { AdditionalUpgrades } from './AdditionalUpgrades'
import { LoadingPanel } from '../ui/LoadingPanel'
import { BottleneckLesson } from './BottleneckLesson'
import { UpgradeChoices } from './UpgradeChoices'

export function CalculatorSection({ cpus, gpus, rams, hardwareLoading, onFindOnMarketplace, onSaveBuild }) {
  const [result, setResult] = useState(null)
  const [loading, setLoading] = useState(false)
  const [searchProgress, setSearchProgress] = useState('Проверяем конфигурацию и цены')
  const [error, setError] = useState(null)
  const [choicesOpen, setChoicesOpen] = useState(false)
  const [resaleEditRequest, setResaleEditRequest] = useState(0)
  const editResale = () => { setChoicesOpen(false); setResaleEditRequest(value=>value+1) }

  const handleCalculate = async ({ cpuId, gpuId, ramId, ramManual, game, mode, budget, aiMode, sellMode, targetFps, priceSources, manualCpu, manualGpu, expectedSalePrice }) => {
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
        target_fps: targetFps,
        price_sources: priceSources,
        refresh_avito_prices: true,
        expected_sale_price: expectedSalePrice ?? null,
      }
      const data = await calculateUpgrade(payload, {onProgress:setSearchProgress})
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
      setChoicesOpen(Boolean(data.alternatives?.length) && data.current_fps < targetFps)
    } catch (e) {
      setError(e.message ?? 'Не удалось рассчитать')
      setResult(null)
    } finally {
      setLoading(false)
    }
  }

  const selectChoice = async choice => {
    setChoicesOpen(false)
    setLoading(true)
    setError(null)
    try {
      const config = { ...result.config, refresh_avito_prices: false,
        selected_upgrade_id: choice.kind === 'platform' ? null : choice.id,
        selected_platform: choice.kind === 'platform' ? choice.platform_selection : null }
      const data = await calculateUpgrade(config)
      setResult(previous => ({ ...previous, ...data, config,
        price_search_status: previous.price_search_status,
        price_search_summary: previous.price_search_summary }))
    } catch (e) { setError(e.message ?? 'Вариант больше недоступен. Повторите расчёт.') }
    finally { setLoading(false) }
  }

  const refreshPrices = async (resetResale = false, focusId = null) => {
    setChoicesOpen(false)
    setLoading(true)
    setError(null)
    try {
      const config={...result.config, refresh_avito_prices:true,
        price_lookup_id:focusId,
        expected_sale_price: resetResale ? null : result.config.expected_sale_price,
        selected_upgrade_id:null, selected_platform:null}
      const data=await calculateUpgrade(config, {onProgress:setSearchProgress})
      setResult(previous=>({...previous,...data,config}))
      setChoicesOpen(Boolean(data.alternatives?.length))
    } catch(e) { setError(e.message ?? 'Не удалось обновить цены.') }
    finally { setLoading(false) }
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
          resaleEditRequest={resaleEditRequest}
        />
      )}

      {error && (
        <div className="text-sm text-red-400 border border-red-400/30 rounded-md px-3 py-2">
          {error}
        </div>
      )}

      {loading && <LoadingPanel title="Ищем ограничение и цены" description={searchProgress}/>}
      {result && !loading && (
        <div className="space-y-6 result-reveal">
          {/* Визуализация bottleneck */}
          <BottleneckVisualization 
            result={result} 
            cpuName={result.cpuName} 
            gpuName={result.gpuName} 
          />
          <BottleneckLesson result={result}/>
          
          {/* Результат с ценой и апгрейдом */}
          <CalculatorResult
            result={result}
            onFind={onFindOnMarketplace}
            onSave={() => onSaveBuild(result)}
            onCompare={result.alternatives?.length ? () => setChoicesOpen(true) : null}
            onResolveResale={editResale}
            onRefreshPrices={() => refreshPrices()}
          />
          <UpgradeChoices open={choicesOpen} choices={result.alternatives || []} targetFps={result.target_fps} currentFps={result.current_fps} onSelect={selectChoice} onClose={() => setChoicesOpen(false)} resaleNotice={result.resale_notice} onResolveResale={editResale} onRetryResale={() => refreshPrices(true)} onLookupPrice={choice => refreshPrices(false, choice.id)}/>
          
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
