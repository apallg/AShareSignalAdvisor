"""
QmtBroker — 对接迅投 miniQMT 真实交易接口。
封装 xtquant.XtQuantTrader，实现 BaseBroker 接口。
需要：miniQMT 已启动、xtquant 已安装、账户已登录。
"""
import logging
import time
import threading
from datetime import datetime
from .base import BaseBroker

logger = logging.getLogger(__name__)

STATUS_MAP = {48: "pending", 50: "pending", 56: "filled", 57: "cancelled", 52: "rejected"}

BUY_ORDER_TYPES = (23, 24)
FIX_PRICE_TYPE = 11
MARKET_PRICE_TYPE = 12


class QmtBroker(BaseBroker):
    def __init__(self, userdata_dir, account, session_id=123456, commission_rate=0.0003, stamp_duty=0.001):
        self._userdata_dir = userdata_dir
        self._account = str(account)
        self._session_id = int(session_id)
        self._commission_rate = commission_rate
        self._stamp_duty = stamp_duty
        self._stock_account = None

        self._trader = None
        self._callback = None
        self._connected = False
        self._account_id = f"QMT-{self._account}"

        self._orders = {}
        self._trades = []
        self._positions = {}
        self._asset = {}

        self._lock = threading.Lock()
        self._last_sync = {}  # method → timestamp
        self._event_thread = None

    def connect(self):
        try:
            from xtquant.xttrader import XtQuantTrader
            from xtquant.xttype import StockAccount
        except ImportError:
            raise RuntimeError(
                "xtquant 未安装，请从 QMT 安装目录安装：\n"
                "pip install {QMT_DIR}/bin.x64/xtquant-*.whl\n"
                "或参考 https://dict.thinktrader.net"
            )

        # 清理可能残留的会话锁文件（避免 connect 返回 -1）
        self._cleanup_stale_locks()

        self._stock_account = StockAccount(self._account, 'STOCK')
        self._trader = XtQuantTrader(self._userdata_dir, self._session_id)
        self._callback = _TraderCallback(self)
        self._trader.register_callback(self._callback)
        self._trader.start()
        connect_result = self._trader.connect()

        if connect_result == 0:
            self._connected = True
            self._sync_positions()
            self._sync_asset()
            # 启动后台线程处理 QMT 事件循环（心跳 + 回调）
            self._event_thread = threading.Thread(
                target=self._trader.run_forever, daemon=True, name="qmt-event"
            )
            self._event_thread.start()
            logger.info(f"QmtBroker 已连接, 账户: {self._stock_account}, 资产: {self._asset}")
        else:
            logger.error(f"QmtBroker 连接失败, 返回码: {connect_result}")
            return False

        return True

    def _cleanup_stale_locks(self):
        """清理上次会话可能残留的锁文件，避免 session_id 被锁定"""
        import os
        prefixes = (
            f"down_queue_win_{self._session_id}",
            f"up_queue_win_{self._session_id}",
            f"lock_down_queue_win_{self._session_id}",
            f"lock_up_queue_win_{self._session_id}",
        )
        try:
            for name in os.listdir(self._userdata_dir):
                if name.startswith(prefixes):
                    try:
                        os.remove(os.path.join(self._userdata_dir, name))
                        logger.debug(f"清理残留锁文件: {name}")
                    except Exception:
                        pass
        except Exception:
            pass

    def disconnect(self):
        self._connected = False
        if self._trader:
            self._trader.stop()
            self._trader = None
        self._event_thread = None

    @property
    def connected(self):
        return self._connected

    @property
    def account_id(self):
        return self._account_id

    @staticmethod
    def _normalize_symbol(symbol):
        """补齐交易所后缀：600879 → 600879.SH, 000001 → 000001.SZ"""
        symbol = symbol.strip()
        if "." in symbol:
            return symbol
        from core.data_sources.miniqmt_source import MiniQmtSource
        return MiniQmtSource.to_xtcode(symbol)

    def place_order(self, symbol, name, side, quantity, price_type, price=None):
        if not self._connected:
            raise RuntimeError("QMT Broker 未连接")

        try:
            from xtquant import xtconstant
        except ImportError:
            raise RuntimeError("xtquant 未安装")

        symbol = self._normalize_symbol(symbol)

        if side == "buy":
            order_type = xtconstant.STOCK_BUY
        elif side == "sell":
            order_type = xtconstant.STOCK_SELL
        else:
            raise ValueError(f"不支持的交易方向: {side}")

        if price_type == "market" or not price or float(price) <= 0:
            price_type_xt = xtconstant.FIX_PRICE
            try:
                from xtquant import xtdata
                tick = xtdata.get_full_tick([symbol])
                if tick and symbol in tick:
                    t = tick[symbol]
                    price = float(t.get("lastPrice", 0) or t.get("lastClose", 0) or 0)
                if not price or price <= 0:
                    detail = xtdata.get_instrument_detail(symbol)
                    if detail:
                        price = float(detail.get("PreClose", 0) or detail.get("LastPrice", 0) or 0)
            except Exception:
                pass
            if not price or price <= 0:
                raise RuntimeError(f"无法获取 {symbol} 的最新价，请使用限价单")
        else:
            price_type_xt = xtconstant.FIX_PRICE

        order_id = self._trader.order_stock(
            self._stock_account, symbol, order_type, int(quantity),
            price_type_xt, float(price), "Apallg投研", name or symbol
        )

        if order_id < 0:
            logger.error(f"QMT 下单失败: {symbol} {side} {quantity}股, 返回码: {order_id}")
            raise RuntimeError(f"QMT 下单失败, 返回码: {order_id}")

        order = {
            "id": str(order_id),
            "symbol": symbol,
            "name": name,
            "side": side,
            "quantity": int(quantity),
            "price_type": price_type,
            "price": float(price) if price else 0,
            "filled_qty": 0,
            "filled_price": 0,
            "status": "pending",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        with self._lock:
            self._orders[str(order_id)] = order

        self._persist_order(order)
        logger.info(f"QMT下单: {symbol} {side} {quantity}股 @ {price if price else '市价'} → {order_id}")
        return str(order_id)

    def cancel_order(self, order_id):
        if not self._connected:
            return False
        result = self._trader.cancel_order(int(order_id))
        if result == 0:
            with self._lock:
                order = self._orders.get(str(order_id))
                if order:
                    order["status"] = "cancelled"
                    order["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    self._persist_order(order)
            return True
        return False

    def get_order(self, order_id):
        with self._lock:
            return self._orders.get(str(order_id))

    def get_orders(self, status=None):
        self._sync_orders()
        with self._lock:
            orders = list(self._orders.values())
        if status:
            orders = [o for o in orders if o["status"] == status]
        return orders

    def get_trades(self, symbol=None):
        self._sync_trades()
        with self._lock:
            trades = list(self._trades)
        if symbol:
            trades = [t for t in trades if t["symbol"] == symbol]
        return trades

    def get_positions(self):
        self._sync_positions()
        with self._lock:
            result = []
            for symbol, p in self._positions.items():
                result.append({
                    "symbol": self._attr(p, "stock_code", symbol),
                    "shares": int(self._attr(p, "volume", 0)),
                    "avg_cost": round(float(self._attr(p, "avg_price", 0)), 3),
                    "current_price": round(float(self._attr(p, "last_price", 0)), 3),
                    "market_value": round(float(self._attr(p, "market_value", 0)), 2),
                    "unrealized_pnl": round(float(self._attr(p, "income", 0)), 2),
                })
            return result

    def get_account(self):
        self._sync_asset()
        self._sync_positions()
        with self._lock:
            asset = self._asset
            positions_snapshot = dict(self._positions)
        if asset is None:
            return {
                "account_id": self._account_id,
                "cash": 0, "frozen": 0, "available": 0,
                "market_value": 0, "total_assets": 0,
                "unrealized_pnl": 0,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        cash = float(self._attr(asset, "cash", 0))
        frozen = float(self._attr(asset, "frozen_cash", 0))
        market_value = float(self._attr(asset, "market_value", 0))
        total = float(self._attr(asset, "total_asset", cash + market_value))
        unrealized = sum(
            float(self._attr(p, "market_value", 0)) - float(self._attr(p, "cost", 0))
            for p in positions_snapshot.values()
        )
        return {
            "account_id": self._account_id,
            "cash": round(cash, 2),
            "frozen": round(frozen, 2),
            "available": round(cash - frozen, 2),
            "market_value": round(market_value, 2),
            "total_assets": round(total, 2),
            "unrealized_pnl": round(unrealized, 2),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

    @staticmethod
    def _attr(obj, name, default=None):
        if isinstance(obj, dict):
            return obj.get(name, default)
        return getattr(obj, name, default)

    def _should_sync(self, method, min_interval=1.0):
        now = time.time()
        last = self._last_sync.get(method, 0)
        if now - last < min_interval:
            return False
        self._last_sync[method] = now
        return True

    def _sync_orders(self):
        if not self._trader or not self._connected:
            return
        if not self._should_sync("orders", 1.0):
            return
        try:
            orders = self._trader.query_stock_orders(self._stock_account) or []
            with self._lock:
                for o in orders:
                    oid = str(self._attr(o, "order_id", ""))
                    order_type = self._attr(o, "order_type", 0)
                    order_status = self._attr(o, "order_status", 0)
                    existing = self._orders.get(oid, {})
                    self._orders[oid] = {
                        "id": oid,
                        "symbol": self._attr(o, "stock_code", existing.get("symbol", "")),
                        "name": existing.get("name", ""),
                        "side": "buy" if order_type in BUY_ORDER_TYPES else "sell",
                        "quantity": int(self._attr(o, "order_volume", 0)),
                        "price_type": "market" if self._attr(o, "price_type", 0) == MARKET_PRICE_TYPE else "limit",
                        "price": float(self._attr(o, "price", 0)),
                        "filled_qty": int(self._attr(o, "traded_volume", 0)),
                        "filled_price": float(self._attr(o, "traded_price", 0)),
                        "status": STATUS_MAP.get(order_status, "pending"),
                        "created_at": existing.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                        "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    }
        except Exception as e:
            logger.debug(f"同步委托失败: {e}")

    def _sync_trades(self):
        if not self._trader or not self._connected:
            return
        if not self._should_sync("trades", 1.0):
            return
        try:
            trades = self._trader.query_stock_trades(self._stock_account) or []
            with self._lock:
                for t in trades:
                    tid = str(self._attr(t, "traded_id", ""))
                    if not any(ex.get("id") == tid for ex in self._trades):
                        self._trades.append({
                            "id": tid,
                            "order_id": str(self._attr(t, "order_id", "")),
                            "symbol": self._attr(t, "stock_code", ""),
                            "name": "",
                            "side": "buy" if self._attr(t, "order_type", 0) in BUY_ORDER_TYPES else "sell",
                            "price": round(float(self._attr(t, "traded_price", 0)), 3),
                            "quantity": int(self._attr(t, "traded_volume", 0)),
                            "amount": round(float(self._attr(t, "traded_amount", 0)), 2),
                            "commission": 0,
                            "stamp_duty": 0,
                            "trade_time": str(self._attr(t, "traded_time", "")),
                        })
        except Exception as e:
            logger.debug(f"同步成交失败: {e}")

    def _sync_positions(self):
        if not self._trader or not self._connected:
            return
        if not self._should_sync("positions", 1.0):
            return
        try:
            positions = self._trader.query_stock_positions(self._stock_account) or []
            with self._lock:
                self._positions = {}
                for p in positions:
                    code = self._attr(p, "stock_code", "")
                    if code:
                        self._positions[code] = p
        except Exception as e:
            logger.debug(f"同步持仓失败: {e}")

    def _sync_asset(self):
        if not self._trader or not self._connected:
            return
        if not self._should_sync("asset", 1.0):
            return
        try:
            asset = self._trader.query_stock_asset(self._stock_account)
            if asset is not None:
                with self._lock:
                    self._asset = asset
        except Exception as e:
            logger.debug(f"同步资产失败: {e}")

class _TraderCallback:
    def __init__(self, broker):
        self._broker = broker

    def on_stock_order(self, order):
        oid = str(self._broker._attr(order, "order_id", ""))
        status = self._broker._attr(order, "order_status", 48)
        order_type = self._broker._attr(order, "order_type", 0)
        with self._broker._lock:
            existing = self._broker._orders.get(oid, {})
            self._broker._orders[oid] = {
                "id": oid,
                "symbol": self._broker._attr(order, "stock_code", existing.get("symbol", "")),
                "name": existing.get("name", ""),
                "side": "buy" if order_type in BUY_ORDER_TYPES else "sell",
                "quantity": int(self._broker._attr(order, "order_volume", 0)),
                "price_type": "market" if self._broker._attr(order, "price_type", 0) == MARKET_PRICE_TYPE else "limit",
                "price": float(self._broker._attr(order, "price", 0)),
                "filled_qty": int(self._broker._attr(order, "traded_volume", 0)),
                "filled_price": float(self._broker._attr(order, "traded_price", 0)),
                "status": STATUS_MAP.get(status, "pending"),
                "created_at": existing.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
        self._broker._persist_order(self._broker._orders[oid])
        self._broker._sync_positions()

    def on_stock_trade(self, trade):
        tid = str(self._broker._attr(trade, "traded_id", ""))
        with self._broker._lock:
            if not any(t.get("id") == tid for t in self._broker._trades):
                entry = {
                    "id": tid,
                    "order_id": str(self._broker._attr(trade, "order_id", "")),
                    "symbol": self._broker._attr(trade, "stock_code", ""),
                    "name": "",
                    "side": "buy" if self._broker._attr(trade, "order_type", 0) in BUY_ORDER_TYPES else "sell",
                    "price": round(float(self._broker._attr(trade, "traded_price", 0)), 3),
                    "quantity": int(self._broker._attr(trade, "traded_volume", 0)),
                    "amount": round(float(self._broker._attr(trade, "traded_amount", 0)), 2),
                    "commission": 0,
                    "stamp_duty": 0,
                    "trade_time": str(self._broker._attr(trade, "traded_time", "")),
                }
                self._broker._trades.append(entry)
                self._broker._persist_trade(entry)

    def on_stock_asset(self, asset):
        with self._broker._lock:
            self._broker._asset = asset

    def on_stock_position(self, position):
        code = self._broker._attr(position, "stock_code", "")
        if code:
            with self._broker._lock:
                self._broker._positions[code] = position

    def on_connected(self):
        logger.info("QMT 连接已建立")

    def on_disconnected(self):
        logger.warning("QMT 连接已断开")
        self._broker._connected = False

    def on_cancel_error(self, order_id, msg):
        logger.error(f"QMT 撤单失败 [{order_id}]: {msg}")

    def on_order_error(self, order_id, msg):
        logger.error(f"QMT 下单失败 [{order_id}]: {msg}")
