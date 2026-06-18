from .base import BaseBroker
from .fake_broker import FakeBroker

def create_broker(broker_type="fake", **kwargs):
    if broker_type == "fake":
        return FakeBroker(**kwargs)
    raise ValueError(f"不支持的经纪商类型: {broker_type}")
