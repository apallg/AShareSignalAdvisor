"""
实盘策略实现 — 从 strategies/ 目录自动发现 LiveStrategy 子类。
"""
import importlib
import inspect
from pathlib import Path
from .base import LiveStrategy

LIVE_STRATEGIES = {}


def _discover_live_from_registry():
    """扫描 strategies/{classic,hybrid,custom,community}/ 查找 LiveStrategy 子类"""
    import sys
    strat_dir = Path(__file__).parent.parent.parent / "strategies"
    for subdir in ["classic", "hybrid", "custom", "community"]:
        d = strat_dir / subdir
        if not d.exists():
            continue
        for f in sorted(d.glob("*.py")):
            if f.name == "__init__.py":
                continue
            mod_name = f"strategies.{subdir}.{f.stem}"
            sys.modules.pop(mod_name, None)
            try:
                mod = importlib.import_module(mod_name)
                for name, obj in inspect.getmembers(mod):
                    if inspect.isclass(obj) and issubclass(obj, LiveStrategy) and obj is not LiveStrategy:
                        key = f"{subdir}/{f.stem}"
                        LIVE_STRATEGIES[key] = obj
            except Exception:
                pass


def reload_live_strategies():
    LIVE_STRATEGIES.clear()
    _discover_live_from_registry()


_discover_live_from_registry()
