import { Button } from '../ui/Button'

export function SavedBuildsSection({ builds, onClear }) {
  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-medium text-accent">Мои сохранённые сборки</h2>
        {builds.length > 0 && (
          <Button variant="danger" onClick={onClear}>Очистить всё</Button>
        )}
      </div>

      {builds.length === 0 ? (
        <p className="text-sm text-gray-500">Пока ничего не сохранено.</p>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {builds.map((b) => (
            <div key={b.id} className="bg-card border border-border rounded-lg p-4 text-sm space-y-1">
              <div className="font-medium">
                {b.cpuName ?? 'CPU'} + {b.gpuName ?? 'GPU'}
              </div>
              <div className="text-gray-400">
                {b.game} · {b.mode === 'cybersport' ? 'Киберспорт' : 'High'}
              </div>
              <div className="text-accent">
                {b.current_fps} → {b.upgraded_fps} FPS ({b.bottleneck})
              </div>
            </div>
          ))}
        </div>
      )}
    </section>
  )
}