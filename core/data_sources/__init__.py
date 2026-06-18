"""
数据源注册中心和工厂
"""
from typing import Dict, Type
from core.data_sources.base import BaseRealtimeSource

_registry: Dict[str, Type[BaseRealtimeSource]] = {}
_instances: Dict[str, BaseRealtimeSource] = {}
_active_source: str = "新浪财经 (实时)"


def register(name: str, source_cls: Type[BaseRealtimeSource]):
    _registry[name] = source_cls


def get_source(name: str) -> BaseRealtimeSource:
    if name not in _instances:
        if name not in _registry:
            name = list(_registry.keys())[0]
        _instances[name] = _registry[name]()
    return _instances[name]


def list_sources() -> list:
    return list(_registry.keys())


def get_active_source() -> str:
    return _active_source


def set_active_source(name: str):
    global _active_source
    if name in _registry:
        _active_source = name


def _init():
    from core.data_sources.sina_source import SinaSource
    from core.data_sources.tencent_source import TencentSource
    register("腾讯财经 (实时)", TencentSource)
    register("新浪财经 (实时)", SinaSource)


_init()
