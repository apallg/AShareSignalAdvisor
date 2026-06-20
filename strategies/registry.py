"""策略注册表——自动扫描 + 热拔插"""
import importlib
import inspect
from pathlib import Path

_registry = {}

# 策略中英文名称映射
PARAM_DESCRIPTIONS = {
    'fast': '快线周期',
    'slow': '慢线周期',
    'period': '计算周期',
    'std': '标准差倍数',
    'devfactor': '标准差倍数',
    'stop_loss': '止损(%)',
    'take_profit': '止盈(%)',
    'entry_z': '入场Z分数',
    'exit_z': '离场Z分数',
    'momentum_days': '动量天数',
    'ma_period': '均线周期',
    'entry_period': '入场周期',
    'exit_period': '离场周期',
    'atr_period': 'ATR周期',
    'atr_multiple': 'ATR倍数',
    'lookback': '回溯周期',
    'short': '短期均线',
    'mid': '中期均线',
    'long': '长期均线',
    'grids': '网格数量',
    'spacing': '网格间距(%)',
    'vol_threshold': '波动率阈值',
    'rebalance_days': '调仓周期(天)',
    'ai_threshold': 'AI评分阈值',
    'tech_weight': '技术权重',
    'ai_weight': 'AI权重',
    'sentiment_weight': '情绪权重',
    'threshold': '综合阈值',
    'buy_prob': '买入概率阈值',
    'sell_prob': '卖出概率阈值',
    'check_interval': '检查间隔(秒)',
    'others_gain_threshold': '同板块涨幅阈值(%)',
    'target_col': '目标列名',
    'sector_cols': '板块列名',
    'buy_threshold': '买入阈值',
    'sell_threshold': '卖出阈值',
    'entry_threshold': '入场阈值',
    'exit_threshold': '离场阈值',
}

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
            info = {'name': name, 'default': value, 'type': 'str', 'desc': PARAM_DESCRIPTIONS.get(name, '')}
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


def _find_live_key(mod, subdir, f_stem, zh_name):
    """在模块中查找 LiveStrategy 子类，返回 live key"""
    for name, obj in inspect.getmembers(mod):
        if inspect.isclass(obj) and obj.__name__ != 'LiveStrategy':
            try:
                from execution.live.base import LiveStrategy
                if issubclass(obj, LiveStrategy):
                    return f"{subdir}/{f_stem}"
            except Exception:
                pass
    return None


def list_strategies():
    result = {}
    for name, info in _registry.items():
        result[name] = {
            'name': info['name'],
            'description': info['description'],
            'tags': info['tags'],
            'params': info['params'],
            'live_key': info.get('live_key'),
        }
    return result


def auto_discover():
    import sys
    base = Path(__file__).parent
    _registry.clear()
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
            mod_name = 'strategies.' + subdir + '.' + f.stem
            # 清除旧缓存，确保删除文件后模块不残留
            sys.modules.pop(mod_name, None)
            try:
                mod = importlib.import_module(mod_name)
                # 记录此模块中找到的 live_key，处理显式 register() 用不同名称的情况
                found_live_key = None
                for name, obj in inspect.getmembers(mod):
                    if inspect.isclass(obj):
                        from strategies.base import BaseStrategy
                        if issubclass(obj, BaseStrategy) and obj is not BaseStrategy:
                            # classic/hybrid 用类名映射，custom/community 用文件名
                            if subdir in ('custom', 'community'):
                                zh_name = f.stem
                            else:
                                zh_name = _STRATEGY_ZH_NAMES.get(name, name)
                            if zh_name not in _registry:
                                register(obj, name=zh_name, desc=subdir + '/' + f.stem)
                            live_key = _find_live_key(mod, subdir, f.stem, zh_name)
                            if live_key and zh_name in _registry:
                                _registry[zh_name]['live_key'] = live_key
                                found_live_key = live_key
                # 同步 live_key 到同名类但被显式 register() 注册的其他条目
                if found_live_key:
                    for entry_name, entry_info in list(_registry.items()):
                        if 'live_key' not in entry_info or not entry_info.get('live_key'):
                            try:
                                mod_cls = dict(inspect.getmembers(mod))
                                for cls_name, cls_obj in mod_cls.items():
                                    if inspect.isclass(cls_obj) and cls_obj is entry_info.get('class'):
                                        _registry[entry_name]['live_key'] = found_live_key
                                        break
                            except Exception:
                                pass
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    '策略注册 加载 ' + f.name + ' 失败: ' + str(e))
    return _registry


auto_discover()
