from datetime import datetime
from zoneinfo import ZoneInfo

BEIJING_TZ = ZoneInfo("Asia/Shanghai")


def now_beijing() -> datetime:
    # Store local Beijing wall-clock time; keep naive for SQLite DateTime compatibility.
    return datetime.now(BEIJING_TZ).replace(tzinfo=None)
