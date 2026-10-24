import { useState } from 'react'
import { useHardware } from './hooks/useHardware'
import { useListings } from './hooks/useListings'
import { useSavedBuilds } from './hooks/useSavedBuilds'
import { CalculatorSection } from './components/calculator/CalculatorSection'
import { MarketplaceSection } from './components/marketplace/MarketplaceSection'
import { SavedBuildsSection } from './components/saved/SavedBuildsSection'

export default function App() {
  const [activeTab, setActiveTab] = useState('calculator');
  const { cpus, gpus, loading: hwLoading, error: hwError } = useHardware()
  const { listings, loading: lstLoading, error: lstError, add: addListing } = useListings()
  const { builds, save, clear } = useSavedBuilds()

  return (
    <div className="min-h-full bg-dark text-gray-200">
      <header className="border-b border-border px-6 py-4 flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold text-accent">PC Upgrade MVP</h1>
          <p className="text-sm text-gray-500">Подбор апгрейда и биржа комплектующих</p>
        </div>
        <nav className="flex gap-2 bg-card p-1 rounded-lg">
          <button 
            onClick={() => setActiveTab('calculator')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition ${activeTab === 'calculator' ? 'bg-accent text-black' : 'text-gray-400 hover:text-white'}`}
          >
            Калькулятор
          </button>
          <button 
            onClick={() => setActiveTab('marketplace')}
            className={`px-4 py-2 rounded-md text-sm font-medium transition ${activeTab === 'marketplace' ? 'bg-accent text-black' : 'text-gray-400 hover:text-white'}`}
          >
            Биржа
          </button>
        </nav>
      </header>

      <main className="max-w-4xl mx-auto px-4 py-8">
        {activeTab === 'calculator' && (
          <div className="space-y-14">
            {hwError && <div className="text-red-400">Ошибка загрузки: {hwError.message}</div>}
            <CalculatorSection
              cpus={cpus}
              gpus={gpus}
              hardwareLoading={hwLoading}
              onFindOnMarketplace={() => setActiveTab('marketplace')}
              onSaveBuild={(result) => { if(result) save(result) }}
            />
            <SavedBuildsSection builds={builds} onClear={clear} />
          </div>
        )}

        {activeTab === 'marketplace' && (
          <MarketplaceSection
            listings={listings}
            loading={lstLoading}
            error={lstError}
            onCreate={addListing}
          />
        )}
      </main>
    </div>
  )
}