"""Memoize repeated technical checks within one synchronous selection only."""
from contextvars import ContextVar
from functools import wraps
def clone(value):
    if isinstance(value, dict):
        return {k: clone(v) if isinstance(v, (dict, list, tuple)) else v for k,v in value.items()}
    if isinstance(value, list):
        return [clone(v) for v in value]
    if isinstance(value, tuple):
        return tuple(clone(v) for v in value)
    return value
_cache = ContextVar("selection_checks", default=None)

def selection_scope(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        if _cache.get() is not None:
            return function(*args, **kwargs)
        token = _cache.set({})
        try:
            return function(*args, **kwargs)
        finally:
            _cache.reset(token)
    return wrapped

def memoized_check(function):
    def key(value):
        if value is None or isinstance(value, (str, int, float, bool)):
            return (type(value), value)
        return (type(value), id(value))
    @wraps(function)
    def wrapped(*args, **kwargs):
        cache = _cache.get()
        if cache is None:
            return function(*args, **kwargs)
        cache = cache.setdefault(function, {})
        identity = (tuple(map(key,args)), tuple(sorted((k,key(v)) for k,v in kwargs.items())))
        if identity not in cache:
            result = function(*args, **kwargs)
            if len(cache) < 4096:
                cache[identity] = (args, kwargs, clone(result))
            return result
        return clone(cache[identity][2])
    return wrapped
