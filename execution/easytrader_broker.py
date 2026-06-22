"""
EasytraderBroker — 通过 easytrader 操控同花顺客户端实现实盘交易。
基于 pywinauto GUI 自动化，对接银河证券 (yh_client)。
需要：同花顺客户端已打开并登录，easytrader + pywin32 已安装。
"""
import logging
import threading
from datetime import datetime
from .base import BaseBroker

logger = logging.getLogger(__name__)

STATUS_MAP = {"已报": "pending", "部成": "partial", "已成": "filled",
              "已撤": "cancelled", "废单": "rejected"}


class EasytraderBroker(BaseBroker):
    def __init__(self, user="", password="", exe_path="", commission_rate=0.0003, stamp_duty=0.001):
        self._user = user
        self._password = password
        self._exe_path = exe_path or r"C:\双子星-中国银河证券\Binarystar.exe"
        self._commission_rate = commission_rate
        self._stamp_duty = stamp_duty

        self._trader = None
        self._connected = False
        self._account_id = "EASYT-YH"

        self._lock = threading.Lock()

    def connect(self):
        try:
            import easytrader
        except ImportError:
            raise RuntimeError(
                "easytrader 未安装，请执行: pip install easytrader pywin32"
            )

        try:
            self._trader = easytrader.use("yh_client")
        except Exception as e:
            raise RuntimeError(f"easytrader 初始化失败: {e}")

        try:
            self._trader.connect(self._exe_path)
            logger.info("EasytraderBroker 已连接到同花顺客户端 (银河证券)")
        except Exception as e:
            raise RuntimeError(
                f"连接同花顺客户端失败，请确认客户端已打开: {e}\n"
                f"exe_path: {self._exe_path}"
            )

        self._connected = True
        logger.info("EasytraderBroker 已连接 (客户端已登录)")

        # 切换为 WMCopy 网格策略，避开验证码弹窗
        try:
            from easytrader.grid_strategies import WMCopy
            self._trader.grid_strategy = WMCopy()
            logger.info("EasytraderBroker 已启用 WMCopy 网格策略")
        except Exception as e:
            logger.warning(f"WMCopy 策略设置失败: {e}")

        return True

    def disconnect(self):
        self._connected = False
        if self._trader:
            try:
                self._trader.exit()
            except Exception:
                pass
            self._trader = None

    @property
    def connected(self):
        return self._connected

    @property
    def account_id(self):
        return self._account_id

    def place_order(self, symbol, name, side, quantity, price_type, price=None):
        if not self._connected or self._trader is None:
            raise RuntimeError("EasytraderBroker 未连接")

        qty = int(quantity)
        try:
            if price_type == "market" or not price or float(price) <= 0:
                if side == "buy":
                    order_id = self._trader.market_buy(symbol, qty)
                else:
                    order_id = self._trader.market_sell(symbol, qty)
            else:
                if side == "buy":
                    order_id = self._trader.buy(symbol, float(price), qty)
                else:
                    order_id = self._trader.sell(symbol, float(price), qty)

            order_id_str = str(order_id) if order_id else f"yh_{datetime.now().strftime('%H%M%S%f')}"
        except Exception as e:
            logger.error(f"easytrader 下单失败: {symbol} {side} {qty}股, {e}")
            raise RuntimeError(f"下单失败: {e}")

        order = {
            "id": order_id_str,
            "symbol": symbol,
            "name": name,
            "side": side,
            "quantity": qty,
            "price_type": price_type,
            "price": float(price) if price else 0,
            "filled_qty": 0,
            "filled_price": 0,
            "status": "pending",
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }

        self._persist_order(order)
        logger.info(f"easytrader下单: {symbol} {side} {qty}股 → {order_id_str}")
        return order_id_str

    def cancel_order(self, order_id):
        if not self._connected or self._trader is None:
            return False
        try:
            self._trader.cancel_entrust(str(order_id))
            logger.info(f"easytrader 撤单: {order_id}")
            return True
        except Exception as e:
            logger.error(f"easytrader 撤单失败 [{order_id}]: {e}")
            return False

    def get_order(self, order_id):
        orders = self.get_orders()
        for o in orders:
            if o["id"] == str(order_id):
                return o
        return None

    def get_orders(self, status=None):
        if not self._connected or self._trader is None:
            return []
        try:
            raw = self._trader.today_entrusts or []
        except Exception as e:
            logger.error(f"easytrader 查询委托失败: {e}")
            self._dismiss_captcha()
            return []

        orders = []
        for r in raw:
            oid = str(r.get("合同编号") or r.get("委托编号") or "")
            raw_status = str(r.get("状态") or r.get("委托状态") or "")
            o = {
                "id": oid,
                "symbol": str(r.get("证券代码") or r.get("股票代码") or ""),
                "name": str(r.get("证券名称") or ""),
                "side": "buy" if "买" in str(r.get("操作") or r.get("买卖") or "") else "sell",
                "quantity": int(float(r.get("委托数量") or 0)),
                "price_type": "limit",
                "price": float(r.get("委托价格") or 0),
                "filled_qty": int(float(r.get("成交数量") or 0)),
                "filled_price": float(r.get("成交价格") or 0),
                "status": STATUS_MAP.get(raw_status, "pending"),
                "created_at": str(r.get("委托时间") or r.get("报单时间") or ""),
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            orders.append(o)
        if status:
            orders = [o for o in orders if o["status"] == status]
        return orders

    def get_trades(self, symbol=None):
        if not self._connected or self._trader is None:
            return []
        try:
            raw = self._trader.today_trades or []
        except Exception as e:
            logger.error(f"easytrader 查询成交失败: {e}")
            self._dismiss_captcha()
            return []

        trades = []
        for r in raw:
            t = {
                "id": str(r.get("合同编号") or r.get("成交编号") or ""),
                "order_id": str(r.get("委托编号") or ""),
                "symbol": str(r.get("证券代码") or ""),
                "name": str(r.get("证券名称") or ""),
                "side": "buy" if "买" in str(r.get("操作") or "") else "sell",
                "price": float(r.get("成交价格") or 0),
                "quantity": int(float(r.get("成交数量") or 0)),
                "amount": float(r.get("成交金额") or 0),
                "commission": float(r.get("手续费") or 0),
                "stamp_duty": float(r.get("印花税") or 0),
                "trade_time": str(r.get("成交时间") or ""),
            }
            trades.append(t)
        if symbol:
            trades = [t for t in trades if t["symbol"] == symbol]
        return trades

    def _dismiss_captcha(self):
        """关闭同花顺新版验证码弹窗"""
        try:
            top = self._trader.app.top_window()
            if top.class_name() == "#32770" and top.is_visible():
                # 按取消按钮关闭
                top.child_window(control_id=2, class_name="Button").click()
                return True
        except Exception:
            pass
        return False

    def get_positions(self):
        if not self._connected or self._trader is None:
            return []
        try:
            raw = self._trader.position or []
        except Exception as e:
            logger.error(f"easytrader 查询持仓失败: {e}")
            self._dismiss_captcha()
            return []

        positions = []
        for r in raw:
            code = str(r.get("证券代码") or r.get("股票代码") or "")
            if not code:
                continue
            shares = int(float(r.get("股票余额") or r.get("当前拥股") or r.get("股份余额") or 0))
            if shares <= 0:
                continue
            positions.append({
                "symbol": code,
                "shares": shares,
                "avg_cost": float(r.get("成本价") or r.get("买入均价") or 0),
                "current_price": float(r.get("最新价") or r.get("市价") or 0),
                "market_value": float(r.get("市值") or r.get("参考市值") or 0),
                "unrealized_pnl": float(r.get("浮动盈亏") or r.get("盈亏") or 0),
            })
        return positions

    def _read_balance_from_gui(self):
        main = self._trader._main
        available = 0
        market_value = 0
        total_assets = 0
        unrealized = 0

        def find_val(control_id):
            for w in main.descendants():
                try:
                    if w.control_id() == control_id:
                        return float(w.window_text())
                except Exception:
                    continue
            return 0

        available = find_val(1012)
        market_value = find_val(1014)
        total_assets = find_val(1015)
        unrealized = find_val(1027)

        logger.info(
            f"Easytrader GUI 余额: 总资产={total_assets}, 可用={available}, "
            f"市值={market_value}, 浮动盈亏={unrealized}"
        )
        return {
            "available": available,
            "market_value": market_value,
            "total_assets": total_assets,
            "unrealized_pnl": unrealized,
        }

    def get_account(self):
        if not self._connected or self._trader is None:
            return {
                "account_id": self._account_id,
                "cash": 0, "frozen": 0, "available": 0,
                "market_value": 0, "total_assets": 0,
                "unrealized_pnl": 0,
                "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }

        try:
            gui = self._read_balance_from_gui()
            available = gui["available"]
            total = gui["total_assets"]
            market_value = gui["market_value"]
            unrealized = gui["unrealized_pnl"]
            cash = total - market_value
            frozen = max(cash - available, 0)

            logger.info(
                f"Easytrader 余额读取成功: 总资产={total}, 可用={available}, 市值={market_value}"
            )
        except Exception as e:
            logger.error(f"easytrader 查询资金失败: {e}")
            available = cash = total = market_value = frozen = unrealized = 0

        return {
            "account_id": self._account_id,
            "cash": round(cash, 2),
            "frozen": round(frozen, 2),
            "available": round(available, 2),
            "market_value": round(market_value, 2),
            "total_assets": round(total, 2),
            "unrealized_pnl": round(unrealized, 2),
            "updated_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
