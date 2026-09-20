"""Single source of truth for "now" so every timestamp in the app is
timezone-aware UTC (datetime.utcnow() is deprecated and produces naive
datetimes, which compare incorrectly against aware ones).
"""
import datetime as dt


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)
