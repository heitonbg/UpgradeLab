"""Diagnostic outcomes supplement legacy origin/status; they never verify a price."""
from functools import wraps
import time
import re
from app.core.price_time import iso_utc

OUTCOMES = frozenset({
    'success','no_results','partial','blocked','rate_limited','timeout','network_error',
    'parse_error','parser_drift','unauthorized','access_not_permitted','unavailable',
    'disabled','not_tested',
})

class SourceFailure(RuntimeError):
    """Known public failure. Messages are supplied by our adapter, never raw bodies."""
    def __init__(self, outcome, message, *, http_status=None, attempted=True):
        if outcome not in OUTCOMES:
            raise ValueError('Unknown source outcome')
        super().__init__(message)
        self.outcome=outcome
        self.http_status=http_status
        self.attempted=attempted

def outcome_code(status, *, result_count=None):
    if status in ('timeout','disabled','unavailable'):
        return status
    if status in ('feed','public_page','product_page','browser_page'):
        if result_count is None:
            return 'not_tested'  # Legacy cache lacks a typed result, not a new attempt.
        return 'success' if result_count else 'no_results'
    return 'not_tested'

def http_outcome(code):
    return {401:'unauthorized',403:'blocked',429:'rate_limited',439:'blocked'}.get(code,'unavailable')

def diagnose_source(function):
    @wraps(function)
    def collect(*args,**kwargs):
        started=time.monotonic()
        source,rows,status,message,details=function(*args,**kwargs)
        details=dict(details)
        code=details.get('outcome')
        if code not in OUTCOMES:
            code=outcome_code(status,result_count=len(rows))
            if rows and details.get('error'):
                code='partial'
        payload=args[1] if len(args)>1 else kwargs.get('payload')
        if payload is not None and payload.method in ('browser','discovery') and not rows:
            # Native browser/CDP is fail-closed in this runtime.
            code='disabled'
            details['attempted']=False
        details.update(outcome=code,elapsed_ms=round(max(0,time.monotonic()-started)*1000,3),
                       result_count=len(rows))
        return source,rows,status,message,details
    return collect

def public_outcome(record, *, cached=False):
    code=record.get('outcome')
    if code not in OUTCOMES:
        code=outcome_code(record.get('status'),result_count=record.get('result_count'))
    return {
        'source':record['source'], 'outcome':code, 'message':record.get('message',''),
        'attempted':record.get('attempted'), 'cached':cached,
        'checked_at':iso_utc(record.get('checked_at')), 'elapsed_ms':record.get('elapsed_ms'),
        'result_count':record.get('result_count'), 'http_status':record.get('http_status'),
    }

def public_runtime_message(error):
    # Legacy adapters may raise arbitrary exception text. Only a numeric HTTP
    # hint is safe to expose; URLs, response bodies and credentials are not.
    hint=re.search(r'\bHTTP\s+(\d{3})\b',str(error))
    if hint:
        return f'Источник сообщил HTTP {hint[1]}; данные не подтверждены'
    return 'Источник недоступен: данные не получены или формат не распознан'
