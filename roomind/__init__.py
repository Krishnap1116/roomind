"""Env settings. Secrets live in .env (never committed)."""
import os


def _parse_dotenv(text: str) -> dict:
    out = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k:
            out[k] = v.strip().strip("'\"")
    return out


def _load_dotenv(path: str = "") -> None:
    if not path:
        here = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(os.path.dirname(here), ".env")
    try:
        with open(path, encoding="utf-8") as f:
            content = f.read()
    except OSError:
        return
    for k, v in _parse_dotenv(content).items():
        os.environ.setdefault(k, v)


_load_dotenv()


def _s(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _f(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


MODEL_API_KEY = _s("MODEL_API_KEY")
MODEL_API_BASE = _s("MODEL_API_BASE", "https://api.meta.ai/v1").rstrip("/")
SPARK_MODEL = _s("SPARK_MODEL", "muse-spark-1.3")
SEARCH_API_KEY = _s("SEARCH_API_KEY")
SEARCH_BASE = _s("SEARCH_BASE", "https://api.tavily.com").rstrip("/")
ASK_EFFORT = _s("ASK_EFFORT", "low")
JUDGE_EFFORT = _s("JUDGE_EFFORT", "medium")
JUDGE_IDLE_S = _f("JUDGE_IDLE_S", 5.0)
JUDGE_MAXWAIT_S = _f("JUDGE_MAXWAIT_S", 20.0)
AWAY_TICK_S = _f("AWAY_TICK_S", 60.0)
PRICE_IN_PER_M = _f("PRICE_IN_PER_M", 0.0)
PRICE_OUT_PER_M = _f("PRICE_OUT_PER_M", 0.0)

MAX_ROOM_COST = _f("MAX_ROOM_COST_USD", 5.0)
PAUSED = _s("ROOMIND_PAUSED", "0") == "1"
DB = _s("DATABASE_URL", "roomind.db")
BASE_URL = _s("BASE_URL", "http://localhost:8000").rstrip("/")
