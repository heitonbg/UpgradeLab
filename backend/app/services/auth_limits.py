"""Atomic SQLite auth quotas and single-use work challenges under account attacks.

No passwords, raw account identifiers, or caller-supplied forwarding headers
are stored. Existing recovery counters remain in reset_request_limits.
"""
import hashlib
import ipaddress
import json
import math
import secrets
from datetime import datetime, timedelta
from fastapi import HTTPException
from sqlalchemy import case, delete, or_, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.exc import OperationalError
from app.core.config import settings
from app.db.models import ResetRequestLimit, AuthChallenge

def now():
    """Patchable UTC clock; SQLite keeps the existing naive UTC representation."""
    return datetime.utcnow()

def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()

def client_ip(request):
    # Uvicorn may populate request.client only from explicitly trusted proxies.
    # Never re-parse X-Forwarded-For or X-Real-IP in application code.
    host=request.client.host if request.client else ''
    try:
        if '%' in host:
            return 'unknown'
        address=ipaddress.ip_address(host)
        if isinstance(address,ipaddress.IPv6Address):
            if address.ipv4_mapped:
                return str(address.ipv4_mapped)
            return str(ipaddress.ip_network((address,settings.auth_ipv6_prefix),strict=False))
        return str(address)
    except ValueError:
        return 'unknown'

def _take(db, key, maximum, seconds, current):
    """One atomic insert/update: no read-then-increment admission race."""
    table=ResetRequestLimit
    expired=or_(table.started_at <= current-timedelta(seconds=seconds), table.started_at > current)
    statement=insert(table).values(key_hash=digest(key),started_at=current,attempts=1)
    statement=statement.on_conflict_do_update(
        index_elements=[table.key_hash],
        set_={'started_at':case((expired,current),else_=table.started_at),
              'attempts':case((expired,1),else_=table.attempts+1)},
        where=or_(expired,table.attempts<maximum)
    ).returning(table.attempts)
    if db.execute(statement).first() is not None:
        return 0
    started=db.scalar(select(table.started_at).where(table.key_hash==digest(key)))
    return max(1,math.ceil((started+timedelta(seconds=seconds)-current).total_seconds()))

def _cleanup(db, current):
    retention=max(settings.auth_login_window_seconds,settings.auth_register_window_seconds,
                  settings.auth_password_window_seconds,settings.auth_recovery_window_seconds)
    db.execute(delete(ResetRequestLimit).where(ResetRequestLimit.started_at<=current-timedelta(seconds=retention)))
    db.execute(delete(AuthChallenge).where(AuthChallenge.expires_at<=current))

def _unavailable(db):
    db.rollback()
    raise HTTPException(503,'Сервис входа временно занят. Повторите запрос позже.',
                        headers={'Retry-After':'1','Cache-Control':'no-store'})

def enforce(db, rules):
    """Charge attempts, including successful ones, before expensive password work."""
    try:
        current=now()
        _cleanup(db,current)
        retry=0
        for key,maximum,seconds in rules:
            retry=_take(db,key,maximum,seconds,current)
            if retry:
                break
        db.commit()
    except OperationalError:
        _unavailable(db)
    if retry:
        raise HTTPException(429,f'Слишком много попыток. Повторите через {retry} сек.',
                            headers={'Retry-After':str(retry),'Cache-Control':'no-store'})

def login_attempt(db, request, email, token=None, nonce=None):
    email=email.strip().lower()
    ip=client_ip(request)
    enforce(db,[
        ('login-ip:'+ip,settings.auth_login_ip_limit,settings.auth_login_window_seconds),
        ('login-pair:'+json.dumps([ip,email]),settings.auth_login_pair_limit,settings.auth_login_window_seconds)])
    try:
        current=now()
        retry=_take(db,'login-account:'+email,settings.auth_login_account_limit,
                    settings.auth_login_window_seconds,current)
        if not retry:
            db.commit()
            return
        subject=digest(json.dumps([ip,email]))
        bits=None
        if token and nonce:
            # DELETE RETURNING atomically claims a ticket. Even invalid solutions
            # consume it, so a proof cannot authorize simultaneous/replayed guesses.
            bits=db.execute(delete(AuthChallenge).where(
                AuthChallenge.token_hash==digest(token),AuthChallenge.subject_hash==subject,
                AuthChallenge.expires_at>current).returning(AuthChallenge.bits)).scalar_one_or_none()
        if bits is not None:
            value=int.from_bytes(hashlib.sha256((token+':'+nonce).encode('ascii')).digest(),'big')
            if value < (1 << (256-bits)):
                db.commit()
                return
        token=secrets.token_hex(32)
        db.add(AuthChallenge(token_hash=digest(token),subject_hash=subject,bits=settings.auth_challenge_bits,
                             expires_at=current+timedelta(seconds=settings.auth_challenge_ttl_seconds)))
        db.commit()
    except OperationalError:
        _unavailable(db)
    # Same response and policy for present and absent accounts, before lookup.
    raise HTTPException(429,detail={'message':'Нужно подтвердить запрос входа. Браузер выполнит проверку автоматически; также можно повторить позже.',
        'challenge':{'token':token,'bits':settings.auth_challenge_bits,
                     'expires_in':settings.auth_challenge_ttl_seconds}},
        headers={'Retry-After':str(retry),'Cache-Control':'no-store'})
