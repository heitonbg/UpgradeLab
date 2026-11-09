"""Normalize contact destinations; never accept arbitrary URL schemes."""
import re
from urllib.parse import urlsplit

def normalize_contact(value, kind=None):
    inferred = kind is None
    value=value.strip()
    if kind is None:
        if re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value):kind='email'
        elif re.match(r'^(?:\+|[78]?\s*\(?\d)',value):kind='phone'
        elif re.match(r'^(?:@|(?:https?://)?t\.me/)',value,re.I) or re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}',value):kind='telegram'
        else:return value,None  # Legacy free-text contact: displayed without a link.
    if kind=='telegram':
        username=value
        if value.startswith('@'):username=value[1:]
        elif '/' in value or ':' in value:
            parsed=urlsplit(value if '://' in value else 'https://'+value)
            if parsed.scheme!='https' or parsed.netloc.lower()!='t.me' or parsed.query or parsed.fragment:
                raise ValueError('Нужна ссылка https://t.me/username')
            username=parsed.path.removeprefix('/')
        if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{4,31}',username):
            if inferred and value.startswith('@'):
                return value, None  # Preserve old short free-text contacts without a link.
            raise ValueError('Telegram: 5–32 символа, первая буква, затем буквы, цифры или _')
        return 'https://t.me/'+username.lower(),'telegram'
    if kind=='phone':
        if not re.fullmatch(r'[+\d\s()\-]+',value) or '+' in value[1:]:
            raise ValueError('Некорректный телефон')
        digits=re.sub(r'\D','',value)
        if len(digits)==10:digits='7'+digits
        elif len(digits)==11 and digits[0]=='8':digits='7'+digits[1:]
        if not re.fullmatch(r'7\d{10}',digits):
            raise ValueError('Введите полный российский номер: +7 и 10 цифр')
        return '+'+digits,'phone'
    if kind=='email' and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',value):
        return value,'email'
    raise ValueError('Выберите Telegram или телефон для неоднозначного контакта')
