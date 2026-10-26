export function normalizeModel(value = '') {
  return String(value).toLowerCase()
    .replace(/\((?:r|tm)\)|[™®]/g, '')
    .replace(/@.*$|\b\d+(?:\.\d+)?\s*(?:ghz|mhz)\b/g, '')
    .replace(/\b(?:processor|cpu|six-core|quad-core|eight-core|dual-core)\b/g, '')
    .replace(/\b\d+\s*-?\s*core\b/g, '')
    .replace(/[^a-zа-я0-9]/g, '')
}

export function searchHardware(items, query) {
  const searchKey = value => normalizeModel(value).replace(/amd|intel|nvidia|geforce|radeon|core/g, '')
  const key = searchKey(query)
  if (!key) return items
  return items.filter(item => searchKey(item.name).includes(key))
    .sort((a, b) => {
      const aKey = searchKey(a.name), bKey = searchKey(b.name)
      return (aKey === key ? -1 : bKey === key ? 1 : aKey.length - bKey.length)
    })
}

export function matchHardware(items, name) {
  const key = normalizeModel(name)
  if (!key) return null
  const exact = items.find(item => normalizeModel(item.name) === key)
  if (exact) return exact
  // Remove the vendor branding while preserving model numbers and suffixes.
  const modelKey = value => normalizeModel(value).replace(/^(?:amd|intel|nvidia|ati)/, '').replace(/^(?:geforce|radeon)/, '')
  const candidates = items.filter(item => modelKey(item.name) === modelKey(name))
  return candidates.length === 1 ? candidates[0] : null
}

export function parseSystemReport(text) {
  const trimmed = text.replace(/^\uFEFF/, '').trim()
  if (trimmed.startsWith('{')) {
    const report = JSON.parse(trimmed)
    if (!Array.isArray(report.cpus) || !Array.isArray(report.gpus)) throw new Error('В файле нет сведений о CPU и GPU.')
    return report
  }
  // Backward compatibility with the original text report. Its total is usable
  // memory; do not guess a DDR generation or channel configuration from it.
  const report = { cpus: [], gpus: [], memory: { capacity_gb: null, type: null, channels: null } }
  let section = ''
  for (const line of trimmed.split(/\r?\n/)) {
    if (/^===.*(CPU|процессор)/i.test(line)) section = 'cpus'
    else if (/^===.*(GPU|видеокарт)/i.test(line)) section = 'gpus'
    else if (/^===.*(RAM|оператив|ОЗУ)/i.test(line)) section = 'memory'
    else if (['cpus', 'gpus'].includes(section) && /^(?:Модель|Model)\s*:/i.test(line)) report[section].push({ name: line.replace(/^[^:]+:/, '').trim() })
    else if (section === 'memory' && /^(?:Всего|Total)\s*:/i.test(line)) {
      const match = line.match(/([\d.,]+)\s*(?:GB|ГБ)/i)
      if (match) report.memory.capacity_gb = Math.round(Number(match[1].replace(',', '.')))
    }
  }
  if (!report.cpus.length && !report.gpus.length) throw new Error('Не удалось прочитать отчёт. Загрузите JSON-файл нового скрипта.')
  return report
}
