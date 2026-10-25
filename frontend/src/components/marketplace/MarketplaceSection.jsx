import { useState } from 'react'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { ListingGrid } from './ListingGrid'
import { ListingForm } from './ListingForm'
import { ListingDetail } from './ListingDetail'

export function MarketplaceSection({ listings, loading, error, onCreate }) {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [search, setSearch] = useState('')
  const [typeFilter, setTypeFilter] = useState('all')
  const [conditionFilter, setConditionFilter] = useState('all')
  const [priceMin, setPriceMin] = useState('')
  const [priceMax, setPriceMax] = useState('')
  const [selectedListing, setSelectedListing] = useState(null)

  const handleCreate = async (data) => {
    setIsSubmitting(true)
    try {
      await onCreate(data)
      setIsModalOpen(false)
    } catch (e) {
      alert(e.message)
    } finally {
      setIsSubmitting(false)
    }
  }

  // Фильтрация
  const filteredListings = (listings || []).filter((l) => {
    if (search) {
      const q = search.toLowerCase()
      const haystack = `${l.title} ${l.description || ''}`.toLowerCase()
      if (!haystack.includes(q)) return false
    }
    if (typeFilter !== 'all') {
      const title = l.title.toLowerCase()
      const desc = (l.description || '').toLowerCase()
      const text = `${title} ${desc}`
      const isCpu = /cpu|процессор|ryzen|core\s*\d/i.test(text)
      const isGpu = /gpu|видеокарт|rtx|gtx|rx\s*\d|geforce|radeon/i.test(text)
      if (typeFilter === 'cpu' && !isCpu) return false
      if (typeFilter === 'gpu' && !isGpu) return false
    }
    if (conditionFilter !== 'all') {
      const cond = l.condition === 'Новое' ? 'new' : 'used'
      if (cond !== conditionFilter) return false
    }
    if (priceMin) {
      const price = parseInt(l.price.replace(/\D/g, '')) || 0
      if (price < parseInt(priceMin)) return false
    }
    if (priceMax) {
      const price = parseInt(l.price.replace(/\D/g, '')) || 0
      if (price > parseInt(priceMax)) return false
    }
    return true
  })

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold text-white">Биржа комплектующих</h2>
        <Button onClick={() => setIsModalOpen(true)}>+ Создать лот</Button>
      </div>

      {/* Фильтры */}
      <div className="flex flex-wrap gap-3 items-center">
        <input
          type="text"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder="Поиск по названию..."
          className="flex-1 min-w-[200px] bg-card border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
        <input
          type="number"
          value={priceMin}
          onChange={(e) => setPriceMin(e.target.value)}
          placeholder="От ₽"
          className="w-24 bg-card border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
        <input
          type="number"
          value={priceMax}
          onChange={(e) => setPriceMax(e.target.value)}
          placeholder="До ₽"
          className="w-24 bg-card border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
        />
        <select
          value={typeFilter}
          onChange={(e) => setTypeFilter(e.target.value)}
          className="bg-card border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
        >
          <option value="all">Все типы</option>
          <option value="cpu">Процессоры</option>
          <option value="gpu">Видеокарты</option>
        </select>
        <select
          value={conditionFilter}
          onChange={(e) => setConditionFilter(e.target.value)}
          className="bg-card border border-border rounded-md px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-accent/40"
        >
          <option value="all">Любое состояние</option>
          <option value="new">Новое</option>
          <option value="used">Б/У</option>
        </select>
        {(search || priceMin || priceMax || typeFilter !== 'all' || conditionFilter !== 'all') && (
          <button
            onClick={() => {
              setSearch('')
              setPriceMin('')
              setPriceMax('')
              setTypeFilter('all')
              setConditionFilter('all')
            }}
            className="text-sm text-gray-500 hover:text-gray-300 transition"
          >
            Сбросить
          </button>
        )}
      </div>

      {error && <p className="text-red-400">{error.message}</p>}
      
      <ListingGrid 
        listings={filteredListings} 
        loading={loading} 
        onClick={(listing) => setSelectedListing(listing)}
      />

      {/* Модальное окно создания лота */}
      <Modal open={isModalOpen} onClose={() => setIsModalOpen(false)} title="Новый лот">
        <ListingForm onSubmit={handleCreate} loading={isSubmitting} />
      </Modal>

      {/* Модальное окно деталей лота */}
      {selectedListing && (
        <Modal 
          open={!!selectedListing} 
          onClose={() => setSelectedListing(null)} 
          title={selectedListing.title}
          size="lg"
        >
          <ListingDetail listing={selectedListing} onClose={() => setSelectedListing(null)} />
        </Modal>
      )}
    </section>
  )
}
