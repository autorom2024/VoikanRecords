import isodate


def parse_duration(iso_duration: str) -> str:
    """
    Перетворює ISO 8601 (PT1H2M3S) у нормальний формат часу для відображення.
    Приклади:
        PT1H2M3S -> 1:02:03
        PT59S    -> 0:59
        PT2M5S   -> 2:05
    """
    try:
        td = isodate.parse_duration(iso_duration)
        total_seconds = int(td.total_seconds())
        hours, remainder = divmod(total_seconds, 3600)
        minutes, seconds = divmod(remainder, 60)

        if hours > 0:
            return f"{hours}:{minutes:02d}:{seconds:02d}"
        else:
            return f"{minutes}:{seconds:02d}"
    except Exception:
        return iso_duration or "—"


def parse_duration_to_seconds(iso_duration: str) -> int:
    """
    Перетворює ISO 8601 (PT1H2M3S) у кількість секунд (int).
    Використовується для визначення, чи це Shorts (<= 60 секунд).
    """
    try:
        td = isodate.parse_duration(iso_duration)
        return int(td.total_seconds())
    except Exception:
        return 0
