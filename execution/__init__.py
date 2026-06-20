from .base import BaseBroker
from .fake_broker import FakeBroker
from .qmt_broker import QmtBroker


def create_broker(broker_type="fake", **kwargs):
    if broker_type == "fake":
        return FakeBroker(**kwargs)
    if broker_type == "qmt":
        return QmtBroker(**kwargs)
    raise ValueError(f"不支持的经纪商类型: {broker_type}")
