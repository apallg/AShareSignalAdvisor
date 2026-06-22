"""
StrategyRunner — 实盘策略运行引擎
定时轮询行情 → 计算指标 → 策略产生信号 → 融合过滤 → 自动下单
支持交易时段感知、收盘前强制平仓、多指标信号融合投票
"""
import time
import logging
import threading
from collections import deque
from datetime import datetime
from .strategies import LIVE_STRATEGIES

import config

logger = logging.getLogger(__name__)


class StrategyRunner:
    def __init__(self):
        self._runners = {}  # runner_id → {config, thread, strategy, broker}
        self._signal_log = deque(maxlen=1000)  # 最近信号记录
        self._lock = threading.Lock()
        self._counter = 0

    def list_strategies(self):
        """返回与回测一致的策略列表，标记哪些支持实盘"""
        try:
            from strategies.registry import list_strategies as reg_list, PARAM_DESCRIPTIONS
            all_strats = reg_list()
            result = {}
            for name, info in all_strats.items():
                lk = info.get('live_key')
                live_capable = bool(lk and lk in LIVE_STRATEGIES)
                key = lk or name
                live_params = LIVE_STRATEGIES[lk].params if live_capable else None
                live_param_descs = {k: PARAM_DESCRIPTIONS.get(k, '') for k in live_params} if live_params else None
                result[key] = {
                    "name": info['name'],
                    "description": info['description'],
                    "params": info['params'],
                    "live_capable": live_capable,
                    "live_params": live_params,
                    "live_param_descs": live_param_descs,
                }
            return result
        except Exception:
            from strategies.registry import PARAM_DESCRIPTIONS
            return {
                key: {
                    "name": cls.name, "description": cls.description,
                    "params": [
                        {"name": k, "default": v, "type": "int" if isinstance(v, int) else "float", "desc": ""}
                        for k, v in cls.params.items()
                    ],
                    "live_capable": True,
                    "live_params": cls.params,
                    "live_param_descs": {k: PARAM_DESCRIPTIONS.get(k, "") for k in cls.params},
                }
                for key, cls in LIVE_STRATEGIES.items()
            }

    def start(self, strategy_key, symbol, broker, params=None, interval_sec=60):
        """
        启动一个策略运行器。
        strategy_key: LIVE_STRATEGIES 中的 key
        symbol: 股票代码
        broker: FakeBroker 实例
        params: 策略参数字典
        interval_sec: 轮询间隔秒数
        """
        cls = LIVE_STRATEGIES.get(strategy_key)
        if not cls:
            raise ValueError(f"未知策略: {strategy_key}")

        strategy = cls(**(params or {}))
        runner_id = f"{strategy_key.replace('/', '-')}_{symbol}_{datetime.now().strftime('%H%M%S')}"

        cfg = {
            "id": runner_id,
            "strategy_key": strategy_key,
            "strategy_name": strategy.name,
            "symbol": symbol,
            "params": params or {},
            "interval_sec": interval_sec,
            "status": "starting",
            "status_detail": "starting",
            "started_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "signals": 0,
            "last_signal": None,
            "last_check": None,
            "last_force_close_tag": None,
            "signal_fusion_enabled": config.SIGNAL_FUSION_ENABLED,
            "fusion_mode": config.SIGNAL_FUSION_MODE,
            "fusion_min_confidence": config.SIGNAL_FUSION_MIN_CONFIDENCE,
            "fusion_weights": {
                "MACD": config.SIGNAL_FUSION_WEIGHT_MACD,
                "RSI": config.SIGNAL_FUSION_WEIGHT_RSI,
                "MA": config.SIGNAL_FUSION_WEIGHT_MA,
                "KDJ": config.SIGNAL_FUSION_WEIGHT_KDJ,
                "BB": config.SIGNAL_FUSION_WEIGHT_BB,
                "VOLUME": config.SIGNAL_FUSION_WEIGHT_VOLUME,
            },
            "last_fusion_result": None,
        }

        thread = threading.Thread(
            target=self._run_loop, args=(runner_id, strategy, broker, cfg), daemon=True
        )

        with self._lock:
            self._runners[runner_id] = {"config": cfg, "thread": thread, "strategy": strategy, "broker": broker}

        thread.start()
        logger.info(f"策略运行器已启动: {runner_id}")
        return runner_id

    def stop(self, runner_id):
        with self._lock:
            r = self._runners.get(runner_id)
            if r:
                r["config"]["status"] = "stopped"
                self._runners.pop(runner_id, None)
                return True
        return False

    def get_status(self, runner_id=None):
        with self._lock:
            if runner_id:
                r = self._runners.get(runner_id)
                return r["config"] if r else None
            return [r["config"] for r in self._runners.values()]

    def get_signals(self, limit=50):
        with self._lock:
            items = list(self._signal_log)
            return list(reversed(items[-limit:]))

    def _run_loop(self, runner_id, strategy, broker, cfg):
        try:
            from core.data_fetcher import DataFetcher
            from core.analyzer import Analyzer
            from core.trading_time import is_trading_time, is_force_close_window
            from core.signal_fusion import SignalFusion

            fetcher = DataFetcher()
            cfg["status"] = "running"

            while True:
                with self._lock:
                    if runner_id not in self._runners:
                        break

                try:
                    now = datetime.now()
                    symbol = cfg["symbol"]

                    if not is_trading_time(now):
                        cfg["status_detail"] = "非交易时段"
                        time.sleep(config.TRADING_IDLE_INTERVAL)
                        continue

                    if config.FORCE_CLOSE_ENABLED and is_force_close_window(now, config.FORCE_CLOSE_TIME):
                        cfg["status_detail"] = "收盘前强制平仓窗口"
                        self._force_close_all(runner_id, broker, cfg, strategy)
                        time.sleep(60)
                        continue

                    cfg["status_detail"] = "交易中"
                    end_date = now.strftime("%Y-%m-%d")
                    df = fetcher.get_stock_daily(symbol, "2024-01-01", end_date)

                    if df is None or df.empty:
                        time.sleep(cfg["interval_sec"])
                        continue

                    df = Analyzer.add_indicators(df)
                    signal = strategy.check_signal(df)

                    fusion_result = None
                    if cfg["signal_fusion_enabled"] and signal["action"] in ("buy", "sell"):
                        fusion = SignalFusion(weights=cfg["fusion_weights"])
                        fusion_result = fusion.evaluate(df)
                        cfg["last_fusion_result"] = {
                            "score": fusion_result.score,
                            "action": fusion_result.action,
                            "confidence": fusion_result.confidence,
                            "indicator_votes": fusion_result.indicator_votes,
                            "reasons": fusion_result.reasons,
                        }

                        if cfg["fusion_mode"] == "override":
                            if fusion_result.action in ("buy", "sell"):
                                signal["action"] = fusion_result.action
                                signal["reason"] = f"[融合覆写] {', '.join(fusion_result.reasons[:3])}"
                                signal["size_ratio"] = fusion_result.confidence
                            else:
                                signal["action"] = "hold"
                                continue
                        else:
                            votes = fusion_result.indicator_votes
                            agree = sum(
                                1 for v in votes.values()
                                if (signal["action"] == "buy" and v > 0) or (signal["action"] == "sell" and v < 0)
                            )
                            total = len([v for v in votes.values() if v != 0])
                            if total > 0 and agree / total < cfg["fusion_min_confidence"]:
                                signal["action"] = "hold"
                                logger.info(
                                    f"融合投票抑制信号 [{runner_id}]: {signal.get('reason')} → "
                                    f"指标分歧({agree}/{total})"
                                )
                                continue

                    if signal["action"] in ("buy", "sell"):
                        self._execute(signal, strategy, broker, symbol, cfg)
                        self._log_signal(runner_id, cfg, signal, strategy, fusion_result)

                    cfg["last_check"] = now.strftime("%H:%M:%S")
                except Exception as e:
                    logger.error(f"策略循环错误 [{runner_id}]: {e}")

                time.sleep(cfg["interval_sec"])

        except Exception as e:
            logger.error(f"策略运行器异常 [{runner_id}]: {e}")
        finally:
            cfg["status"] = "stopped"
            cfg["stopped_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def _execute(self, signal, strategy, broker, symbol, cfg):
        from core.data_fetcher import DataFetcher
        fetcher = DataFetcher()
        q = fetcher.get_realtime_quote(symbol)
        price = float(q.get("最新价", 0))
        signal["exec_price"] = price
        name = cfg.get("stock_name", "")
        if not name:
            name = q.get("名称", symbol)
            cfg["stock_name"] = name

        broker_positions = {p["symbol"]: p for p in broker.get_positions()}
        broker_has = broker_positions.get(symbol, {}).get("shares", 0)
        account = broker.get_account()

        if signal["action"] == "buy":
            if broker_has > 0:
                logger.info(f"跳过买入 {symbol}: 已有持仓 {broker_has}股")
                return
            cash = account["cash"]
            size_ratio = signal.get("size_ratio", 1.0)
            est_cost = price * 100  # 一手约价
            if est_cost <= 0:
                return
            max_shares = int(cash * size_ratio / price / 100) * 100  # 按手取整
            if max_shares < 100:
                logger.info(f"跳过买入 {symbol}: 资金不足 (可用:{cash}, 需≥{est_cost})")
                return
            broker.place_order(symbol, name, "buy", max_shares, "market")
            strategy.on_fill("buy", price, max_shares)

        elif signal["action"] == "sell":
            if broker_has <= 0:
                logger.info(f"跳过卖出 {symbol}: 无持仓")
                return
            broker.place_order(symbol, name, "sell", broker_has, "market")
            strategy.on_fill("sell", price, broker_has)

    def _force_close_all(self, runner_id, broker, cfg, strategy):
        today_key = datetime.now().strftime("%Y%m%d")
        force_tag = f"FORCE_CLOSE_{today_key}"
        if cfg.get("last_force_close_tag") == force_tag:
            return

        symbol = cfg["symbol"]
        broker_positions = {p["symbol"]: p for p in broker.get_positions()}
        shares = broker_positions.get(symbol, {}).get("shares", 0)
        if shares <= 0:
            return

        from core.data_fetcher import DataFetcher
        q = DataFetcher().get_realtime_quote(symbol)
        price = float(q.get("最新价", 0))
        name = cfg.get("stock_name", symbol)

        broker.place_order(symbol, name, "sell", shares, "market")
        strategy.on_fill("sell", price, shares)
        cfg["last_force_close_tag"] = force_tag

        signal = {
            "action": "sell",
            "size_ratio": 1.0,
            "reason": config.FORCE_CLOSE_REASON,
            "exec_price": price,
            "force_close": True,
        }
        self._log_signal(runner_id, cfg, signal, strategy)
        logger.warning(f"收盘前强制平仓 [{runner_id}]: {symbol} {shares}股 @ {price}")

    def _current_price(self, symbol):
        try:
            from core.data_fetcher import DataFetcher
            q = DataFetcher().get_realtime_quote(symbol)
            return float(q.get("最新价", 0))
        except Exception:
            return 0

    def _log_signal(self, runner_id, cfg, signal, strategy, fusion_result=None):
        current_price = signal.get("exec_price", self._current_price(cfg["symbol"]))
        entry = {
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "runner_id": runner_id,
            "strategy": cfg["strategy_name"],
            "symbol": cfg["symbol"],
            "action": signal["action"],
            "reason": signal["reason"],
            "price": current_price,
            "position_after": strategy.position,
            "force_close": signal.get("force_close", False),
        }
        if fusion_result is not None:
            entry["fusion_score"] = fusion_result.score
            entry["fusion_confidence"] = fusion_result.confidence
            entry["fusion_votes"] = fusion_result.indicator_votes

        with self._lock:
            self._signal_log.append(entry)
            cfg["signals"] += 1
            cfg["last_signal"] = entry

        logger.info(f"信号 [{runner_id}]: {signal['action'].upper()} {cfg['symbol']} — {signal['reason']}")


_runner = None


def get_runner():
    global _runner
    if _runner is None:
        _runner = StrategyRunner()
    return _runner
