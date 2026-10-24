import { useState } from 'react'
import { Button } from '../ui/Button'
import { Modal } from '../ui/Modal'
import { ListingGrid } from './ListingGrid'
import { ListingForm } from './ListingForm'

export function MarketplaceSection({ listings, loading, error, onCreate }) {
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)

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

  return (
    <section className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-2xl font-semibold text-white">Биржа комплектующих</h2>
        <Button onClick={() => setIsModalOpen(true)}>+ Создать лот</Button>
      </div>

      {error && <p className="text-red-400">{error.message}</p>}
      
      <ListingGrid listings={listings} loading={loading} />

      <Modal open={isModalOpen} onClose={() => setIsModalOpen(false)} title="Новый лот">
        <ListingForm onSubmit={handleCreate} loading={isSubmitting} />
      </Modal>
    </section>
  )
}