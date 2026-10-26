import { Button } from '../ui/Button'
import { Card } from '../ui/Card'

function contactLink(contact) {
  const value = contact.trim()
  const telegram = value.match(/^(?:@|(?:https?:\/\/)?t\.me\/)([a-zA-Z0-9_]{5,32})$/i)
  if (telegram) return { href: `https://t.me/${telegram[1]}`, label: 'Написать в Telegram ↗' }
  const phone = value.replace(/[\s()+-]/g, '')
  if (/^\d{10,15}$/.test(phone)) return { href: `tel:+${phone}`, label: 'Позвонить ↗' }
  const email = value.match(/^[^\s@]+@[^\s@]+\.[^\s@]+$/)
  if (email) return { href: `mailto:${value}`, label: 'Написать на почту ↗' }
  return null
}

export function ListingDetail({ listing, onClose }) {
  const link = contactLink(listing.contact)
  return <div className="space-y-4 animate-slide-up"><Card className="space-y-4"><div className="flex justify-between gap-3"><span className="text-xs px-2 py-1 rounded bg-border text-gray-300">{listing.condition}</span><strong className="text-2xl text-accent">{listing.price}</strong></div><p className="text-sm text-gray-300 whitespace-pre-wrap">{listing.description || 'Описание не добавлено.'}</p><p className="text-xs text-gray-500">Опубликовано {new Date(listing.created_at).toLocaleString('ru-RU')}</p></Card><div className="p-4 rounded-lg bg-card border border-border"><p className="text-xs text-gray-500 mb-2">КОНТАКТ ПРОДАВЦА</p><p className="text-white font-medium break-all">{listing.contact}</p>{link && <a href={link.href} target={link.href.startsWith('https:') ? '_blank' : undefined} rel={link.href.startsWith('https:') ? 'noopener noreferrer' : undefined} className="inline-block mt-4 text-accent text-sm font-semibold hover:underline">{link.label}</a>}</div><Button variant="secondary" onClick={onClose}>Закрыть</Button></div>
}
