"""UTC price clock, ISO parsing and existing TTLs.

SQLite DateTime columns retain naive UTC for backward compatibility. All
comparisons happen on aware UTC; only persistence/query bounds use naive UTC.
"""
from datetime import datetime, timedelta, timezone
import re

OFFER_TTL = timedelta(hours=24)
SEARCH_TTL = timedelta(minutes=10)
VERIFICATION_TTL = timedelta(minutes=15)
UNAVAILABLE_TTL = timedelta(minutes=10)
# Existing observation-ingestion tolerance for clocks in external feeds.
OBSERVATION_SKEW = timedelta(minutes=5)

def utc_now():
    """Single patchable wall clock for prices; network deadlines stay monotonic."""
    return datetime.now(timezone.utc)

def as_utc(value):
    """Legacy naive timestamps mean UTC, never the server's local timezone."""
    try:
        if isinstance(value, str):
            value = value.strip()
            if not re.match(r"^\d{4}-\d{2}-\d{2}[Tt ]\d{2}:\d{2}", value):
                return None
            value = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if not isinstance(value, datetime):
            return None
        return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)
    except (ValueError, TypeError, OverflowError):
        return None

def as_naive_utc(value):
    parsed = as_utc(value)
    return parsed.replace(tzinfo=None) if parsed is not None else None

def db_now():
    return as_naive_utc(utc_now())

def iso_utc(value):
    parsed = as_utc(value)
    return parsed.isoformat().replace("+00:00", "Z") if parsed is not None else None

def is_fresh(value, ttl, *, inclusive=False, future_tolerance=timedelta(0), now=None):
    parsed = as_utc(value)
    current = as_utc(now) if now is not None else utc_now()
    if parsed is None or current is None:
        return False
    age = current - parsed
    return age >= -future_tolerance and (age <= ttl if inclusive else age < ttl)

def past_utc(value):
    parsed = as_utc(value)
    return parsed if parsed is not None and parsed <= utc_now() else None

def current_verification(metadata):
    if not isinstance(metadata, dict) or metadata.get("status") != "verified":
        return None
    value = metadata.get("checked_at")
    return iso_utc(value) if is_fresh(value, VERIFICATION_TTL) else None
