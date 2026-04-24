# 📄 файл: utils/formatting.py

def plural_ru(n: int, one: str, few: str, many: str) -> str:
    """
    Склонение существительных по числу для русского языка.
    Пример: plural_ru(3, "запись", "записи", "записей") → "записи"
    """
    if 11 <= (n % 100) <= 19:
        return many
    r = n % 10
    if r == 1:
        return one
    if 2 <= r <= 4:
        return few
    return many


def format_duration_seconds(seconds: int) -> str:
    """Форматирует секунды в читаемую строку."""
    if seconds < 60:
        return f"{seconds} сек"
    if seconds < 3600:
        m = seconds // 60
        return f"{m} {plural_ru(m, 'минута', 'минуты', 'минут')}"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    h_str = f"{h} {plural_ru(h, 'час', 'часа', 'часов')}"
    return f"{h_str} {m} {plural_ru(m, 'минута', 'минуты', 'минут')}" if m else h_str