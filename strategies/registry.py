"""策略注册表——自动扫描 + 热拔插"""
import importlib
import inspect
from pathlib import Path

_registry = {}

# 策略中英文名称映射
_STRATEGY_ZH_NAMES = {
    'GoldenCrossStrategy': '双均线金叉死叉',
    'TurtleStrategy': '海龟交易法则',
    'BollingerStrategy': '布林带反转',
    'BreakoutStrategy': '趋势突破',
    'MeanReversionStrategy': '均值回归',
    'MomentumStrategy': '动量轮动',
    'GridStrategy': '网格交易',
    'LowVolStrategy': '低波风格',
    'ValueStrategy': '价值选股',
    'BullArrangementStrategy': '均线多头排列',
    'AIFilteredStrategy': 'AI过滤增强',
    'SentimentBoostStrategy': '情绪仓位增强',
    'MultiFactorStrategy': '多因子综合',
}


def register(strategy_class, name=None, desc="", tags=None):
    cls_name = name or strategy_class.__name__
    _registry[cls_name] = {
        'class': strategy_class,
        'name': cls_name,
        'description': desc,
        'tags': tags or [],
        'params': _extract_params(strategy_class),
    }
    return strategy_class


def _extract_params(cls):
    """从 backtrader 策略类提取参数定义"""
    params = []
    try:
        p = cls.params
        for name in p.__dict__:
            if name.startswith("_"):
                continue
            value = p.__dict__[name]
            info = {'name': name, 'default': value, 'type': 'str'}
            if isinstance(value, bool):
                info['type'] = 'bool'
            elif isinstance(value, int):
                info['type'] = 'int'
                info['min'] = 1
                info['max'] = 200
            elif isinstance(value, float):
                info['type'] = 'float'
                info['min'] = 0.01
                info['max'] = 50.0
            params.append(info)
    except Exception:
        pass
    return params


def get_strategy(name):
    info = _registry.get(name)
    return info['class'] if info else None


def list_strategies():
    result = {}
    for name, info in _registry.items():
        result[name] = {
            'name': info['name'],
            'description': info['description'],
            'tags': info['tags'],
            'params': info['params'],
        }
    return result


def auto_discover():
    base = Path(__file__).parent
    for subdir in ['classic', 'community', 'custom', 'hybrid']:
        sub_path = base / subdir
        if not sub_path.exists():
            sub_path.mkdir(parents=True, exist_ok=True)
            (sub_path / '__init__.py').write_text('')
            continue
        init_file = sub_path / '__init__.py'
        if not init_file.exists():
            init_file.write_text('')
        for f in sorted(sub_path.glob('*.py')):
            if f.name == '__init__.py':
                continue
            try:
                mod_name = 'strategies.' + subdir + '.' + f.stem
                mod = importlib.import_module(mod_name)
                for name, obj in inspect.getmembers(mod):
                    if inspect.isclass(obj):
                        from strategies.base import BaseStrategy
                        if issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
                            if name not in _registry:
                                zh_name = _STRATEGY_ZH_NAMES.get(name, name)
                                register(obj, name=zh_name, desc=subdir + '/' + name)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    '策略注册 加载 ' + f.name + ' 失败: ' + str(e))
    return _registry


auto_discover()
