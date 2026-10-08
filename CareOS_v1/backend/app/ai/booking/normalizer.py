from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo


class NormalizationError(ValueError):
    """Raised when extracted booking data cannot be normalized safely."""


def normalize_datetime(
    date_value: str | None,
    time_value: str | None,
    timezone: str,
    *,
    now: datetime | None = None,
) -> datetime:
    if not date_value:
        raise NormalizationError("date is required")

    if not time_value:
        raise NormalizationError("time is required")

    try:
        tz = ZoneInfo(timezone)
    except Exception as exc:
        raise NormalizationError(f"invalid timezone: {timezone}") from exc

    current = now or datetime.now(tz)

    normalized_date = _normalize_date(date_value, current)
    normalized_time = _normalize_time(time_value)

    local_dt = datetime.combine(
        normalized_date,
        normalized_time,
        tzinfo=tz,
    )

    return local_dt.astimezone(ZoneInfo("UTC"))


import re

MONTHS_AR_EN = {
    "يناير": 1, "فبراير": 2, "مارس": 3, "إبريل": 4, "ابريل": 4, "مايو": 5, "يونيو": 6,
    "يوليو": 7, "أغسطس": 8, "اغسطس": 8, "سبتمبر": 9, "أكتوبر": 10, "اكتوبر": 10,
    "نوفمبر": 11, "ديسمبر": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "jun": 6, "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}

def _normalize_date(value: str, current: datetime):
    value = value.strip().lower()

    if value in {"today", "النهارده", "اليوم"}:
        return current.date()
    if value in {"tomorrow", "بكرة", "غدا", "غداً"}:
        return current.date() + timedelta(days=1)
    if value in {"بعد بكرة", "بعد غد", "بعد غداً"}:
        return current.date() + timedelta(days=2)
    if value in {"بعد أسبوع", "بعد اسبوع", "in a week"}:
        return current.date() + timedelta(days=7)

    if re.match(r"^\d{4}-\d{1,2}-\d{1,2}$", value):
        try:
            return datetime.strptime(value, "%Y-%m-%d").date()
        except ValueError as exc:
            raise NormalizationError(f"unsupported date: {value}") from exc

    m_slash = re.match(r"^(\d{1,2})/(\d{1,2})(?:/(\d{4}))?$", value)
    if m_slash:
        d = int(m_slash.group(1))
        m = int(m_slash.group(2))
        y = int(m_slash.group(3)) if m_slash.group(3) else current.year
        try:
            parsed = datetime(y, m, d).date()
            if not m_slash.group(3) and parsed < current.date():
                parsed = datetime(y + 1, m, d).date()
            return parsed
        except ValueError:
            raise NormalizationError(f"unsupported date: {value}")

    m_text = re.match(r"^(\d{1,2})\s+([a-zA-Z\u0600-\u06FF]+)(?:\s+(\d{4}))?$", value)
    if m_text:
        d = int(m_text.group(1))
        month_str = m_text.group(2).lower()
        y = int(m_text.group(3)) if m_text.group(3) else current.year
        
        if month_str in MONTHS_AR_EN:
            m = MONTHS_AR_EN[month_str]
            try:
                parsed = datetime(y, m, d).date()
                if not m_text.group(3) and parsed < current.date():
                    parsed = datetime(y + 1, m, d).date()
                return parsed
            except ValueError:
                pass

    raise NormalizationError(f"unsupported date: {value}")

def _convert_ampm(h: int, m: int, ampm: str) -> time:
    if h < 1 or h > 12:
        raise NormalizationError("invalid hour for am/pm")
    
    ampm_noon = {"الظهر", "العصر"}
    ampm_pm = {"pm", "مساء", "مساءً", "بالليل"}
    ampm_am = {"am", "الصبح", "صباحا", "صباحًا"}
    
    if ampm in ampm_noon:
        return time(12, m) if h == 12 else time(h + 12, m)
        
    if ampm in ampm_pm:
        if h == 12:
            return time(12, m) if ampm == "pm" else time(0, m)
        return time(h + 12, m)
        
    if ampm in ampm_am:
        if h == 12:
            return time(0, m)
        return time(h, m)
        
    raise NormalizationError("unknown ampm")

def _normalize_time(value: str) -> time:
    value = value.replace("الساعة", "").strip().lower()

    m_24 = re.match(r"^(\d{1,2}):(\d{2})$", value)
    if m_24:
        h, m = int(m_24.group(1)), int(m_24.group(2))
        if 0 <= h <= 23:
             return time(h, m)
        raise NormalizationError(f"invalid hour: {value}")

    m_ampm_colon = re.match(r"^(\d{1,2}):(\d{2})\s*(am|pm|الصبح|صباحا|صباحًا|بالليل|مساء|مساءً|الظهر|العصر)$", value)
    if m_ampm_colon:
        h, m = int(m_ampm_colon.group(1)), int(m_ampm_colon.group(2))
        return _convert_ampm(h, m, m_ampm_colon.group(3))

    m_ampm_flat = re.match(r"^(\d{1,2})\s*(am|pm|الصبح|صباحا|صباحًا|بالليل|مساء|مساءً|الظهر|العصر)?$", value)
    if m_ampm_flat:
        h = int(m_ampm_flat.group(1))
        ampm_str = m_ampm_flat.group(2)
        if not ampm_str:
            raise NormalizationError(f"ambiguous time: {value}; AM/PM is required")
        return _convert_ampm(h, 0, ampm_str)

    raise NormalizationError(f"unsupported time: {value}")
