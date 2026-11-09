export function normalizeContact(raw, kind) {
  const value = raw.trim()
  if (!kind) {
    if (/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) kind = 'email'
    else if (/^(?:\+|[78]?\s*\(?\d)/.test(value)) kind = 'phone'
    else if (/^(?:@|(?:https?:\/\/)?t\.me\/)/i.test(value) || /^[A-Za-z][A-Za-z0-9_]{4,31}$/.test(value)) kind = 'telegram'
    else return null
  }
  if (kind === 'phone') {
    if (!/^[+\d\s()-]+$/.test(value) || value.slice(1).includes('+')) throw Error('Некорректный телефон')
    let digits = value.replace(/\D/g,'')
    if (digits.length === 10) digits = '7' + digits
    else if (digits.length === 11 && digits[0] === '8') digits = '7' + digits.slice(1)
    if (!/^7\d{10}$/.test(digits)) throw Error('Введите полный номер: +7 и 10 цифр')
    return {value:'+' + digits, type:'phone', href:'tel:+' + digits, label:'Позвонить'}
  }
  if (kind === 'telegram') {
    let username = value.replace(/^@/,'')
    if (value.includes('/') || value.includes(':')) {
      let url
      try { url = new URL(value.includes('://') ? value : 'https://' + value) } catch { throw Error('Некорректная ссылка Telegram') }
      if (url.protocol !== 'https:' || url.host !== 't.me' || url.username || url.password || url.search || url.hash) throw Error('Нужна ссылка https://t.me/username')
      username = url.pathname.slice(1)
    }
    if (!/^[A-Za-z][A-Za-z0-9_]{4,31}$/.test(username)) throw Error('Telegram: 5–32 символа, первая буква')
    const href = 'https://t.me/' + username.toLowerCase()
    return {value:href,type:'telegram',href,label:'Написать в Telegram'}
  }
  if (kind === 'email' && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value)) return {value,type:'email',href:'mailto:'+value,label:'Написать на почту'}
  throw Error('Выберите тип контакта')
}

export function contactPreview(value,kind) {
  try { return {contact:normalizeContact(value,kind),error:null} }
  catch (error) { return {contact:null,error:error.message} }
}
