import { useState } from 'react';
import { Button } from './ui/Button';

export function AutoDetectButton({ cpus, gpus, onDetect }) {
  const [detecting, setDetecting] = useState(false);
  const [detectedRam, setDetectedRam] = useState(null);

  const detectGPU = () => {
    try {
      const canvas = document.createElement('canvas');
      const gl = canvas.getContext('webgl') || canvas.getContext('experimental-webgl');
      if (!gl) return null;
      const debugInfo = gl.getExtension('WEBGL_debug_renderer_info');
      if (debugInfo) return gl.getParameter(debugInfo.UNMASKED_RENDERER_WEBGL);
    } catch (e) {
      console.error('WebGL detection failed', e);
    }
    return null;
  };

  const runCpuBenchmark = () => {
    const iterations = 20000000;
    const runs = 3;
    
    // Прогрев
    for (let i = 0; i < 1000000; i++) {
      Math.sqrt(i) * Math.sin(i);
    }
    
    let totalTime = 0;
    for (let r = 0; r < runs; r++) {
      const start = performance.now();
      let operations = 0;
      for (let i = 0; i < iterations; i++) {
        operations += Math.sqrt(i) * Math.sin(i);
      }
      const end = performance.now();
      totalTime += (end - start);
    }
    
    const avgTime = totalTime / runs;
    console.log(`[Бенчмарк] Среднее время: ${avgTime.toFixed(2)} мс`);
    return avgTime;
  };

  const handleDetect = async () => {
    setDetecting(true);
    setDetectedRam(null);

    // 1. GPU
    const gpuRenderer = detectGPU();
    let detectedGpuId = null;
    if (gpuRenderer) {
      try {
        const res = await fetch('/api/detect-gpu', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ renderer_string: gpuRenderer })
        });
        if (res.ok) {
          const data = await res.json();
          if (data.gpu_id) detectedGpuId = data.gpu_id;
        }
      } catch (e) { console.error(e); }
    }

    // 2. CPU + RAM
    const cpuTime = runCpuBenchmark();
    const cpuCores = navigator.hardwareConcurrency || 2;
    const deviceMemory = navigator.deviceMemory; 
    
    console.log(`[Бенчмарк] Ядер: ${cpuCores}, ОЗУ (прибл.): ${deviceMemory || 'неизвестно'} ГБ`);

    let detectedCpuId = null;
    
    try {
      const res = await fetch('/api/detect-cpu', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          benchmark_time_ms: cpuTime,
          cpu_cores: cpuCores,
          device_memory: deviceMemory
        })
      });
      
      if (res.ok) {
        const data = await res.json();
        if (data.cpu_id) detectedCpuId = data.cpu_id;
        if (data.device_memory_gb) setDetectedRam(data.device_memory_gb);
      }
    } catch (e) { console.error(e); }

    onDetect(detectedCpuId, detectedGpuId);
    setDetecting(false);
  };

  return (
    <div className="mb-4 p-4 border border-border rounded-md bg-card/50">
      <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div>
          <p className="text-sm font-medium text-accent">Автоопределение</p>
          <p className="text-xs text-gray-500">
            Видеокарта — по данным WebGL. Процессор — оценка скорости.
            {detectedRam && (
              <span className="block text-accent/80 mt-1">
                Обнаружено ОЗУ: ~{detectedRam} ГБ (браузер округляет)
              </span>
            )}
          </p>
        </div>
        <Button onClick={handleDetect} disabled={detecting} variant="secondary">
          {detecting ? 'Сканирование...' : 'Определить мой ПК'}
        </Button>
      </div>
    </div>
  );
}