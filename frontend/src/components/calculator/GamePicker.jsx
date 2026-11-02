import { useId, useState } from 'react'
import { GAMES } from '../../constants/game'

export function GamePicker({ value, onChange }) {
  const id = useId()
  const [query, setQuery] = useState('')
  const selected = GAMES.find(game => game.value === value)
  const matches = GAMES.filter(game => [game.label, ...(game.aliases || [])].some(name => name.toLowerCase().includes(query.trim().toLowerCase())))
  const options = matches.some(game => game.value === value) ? matches : [selected, ...matches].filter(Boolean)
  return <div className="game-picker">
    <label htmlFor={id}>Игра <small>{GAMES.length} в каталоге</small></label>
    <input type="search" aria-label="Найти игру" placeholder="Поиск по названию игры…" value={query} onChange={event => setQuery(event.target.value)}/>
    <select id={id} value={value} onChange={event => onChange(event.target.value)}>
      {options.map(game => <option key={game.value} value={game.value}>{game.label}</option>)}
    </select>
    {query && <small role="status">Найдено: {matches.length}{!matches.length && '. Текущий выбор сохранён.'}</small>}
    <p className="field-hint">FPS показываем диапазоном. В результате указаны игровые тесты, настройки и способ расчёта для выбранной видеокарты.</p>
  </div>
}
