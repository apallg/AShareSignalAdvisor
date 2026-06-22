"""
MySQL 数据库模块 - 连接管理 + 数据持久化
"""
import json
import threading
import time
from datetime import datetime
from typing import Optional, List, Dict, Any
import pymysql
import pymysql.cursors
import config


def _is_connection_alive(conn):
    """检查连接是否真正可用（socket 非空 + ping 通过）"""
    if conn is None:
        return False
    try:
        sock = getattr(conn, '_sock', None)
        if sock is None:
            return False
        # getsockname 在 socket 已关闭时会抛 OSError
        sock.getsockname()
        conn.ping(reconnect=False)
        return True
    except Exception:
        return False


class Database:
    """MySQL 连接管理器（线程安全 + 自动重连 + 查询重试）"""
    _conn = None
    _lock = threading.Lock()

    @classmethod
    def is_available(cls) -> bool:
        return config.MYSQL_ENABLED

    @classmethod
    def _connect(cls):
        return pymysql.connect(
            host=config.MYSQL_HOST, port=config.MYSQL_PORT,
            user=config.MYSQL_USER, password=config.MYSQL_PASSWORD,
            database=config.MYSQL_DATABASE, charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            autocommit=True,
            connect_timeout=5, read_timeout=30, write_timeout=30,
            ssl={"ssl_disabled": True},
        )

    @classmethod
    def get_connection(cls):
        with cls._lock:
            if not _is_connection_alive(cls._conn):
                try:
                    if cls._conn is not None:
                        cls._conn.close()
                except Exception:
                    pass
                cls._conn = cls._connect()
            return cls._conn

    @classmethod
    def _execute_with_retry(cls, operation, sql, params=(), commit=False):
        """带自动重连重试的查询执行"""
        max_retries = 2
        for attempt in range(max_retries):
            conn = cls.get_connection()
            try:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    if commit:
                        conn.commit()
                    return operation(cur)
            except (pymysql.err.Error, AttributeError, ValueError, OSError):
                if attempt < max_retries - 1:
                    with cls._lock:
                        old = cls._conn
                        cls._conn = None  # 先置空，阻止其他线程拿到坏连接
                        if old is not None:
                            try:
                                # 强制关闭 socket，清理 SSL 会话
                                sock = getattr(old, '_sock', None)
                                if sock is not None:
                                    try:
                                        sock.close()
                                    except Exception:
                                        pass
                                old.close()
                            except Exception:
                                pass
                        cls._conn = cls._connect()
                    time.sleep(0.3)
                    continue
                raise

    @classmethod
    def execute(cls, sql, params=()):
        return cls._execute_with_retry(lambda cur: cur.lastrowid, sql, params, commit=True)

    @classmethod
    def fetchone(cls, sql, params=()):
        return cls._execute_with_retry(lambda cur: cur.fetchone(), sql, params)

    @classmethod
    def fetchall(cls, sql, params=()):
        return cls._execute_with_retry(lambda cur: cur.fetchall(), sql, params)

    @classmethod
    def create_tables(cls):
        sqls = [
            "CREATE TABLE IF NOT EXISTS holdings ("
                "id INT AUTO_INCREMENT PRIMARY KEY,"
            "code VARCHAR(10) NOT NULL, name VARCHAR(50) NOT NULL,"
            "shares INT NOT NULL DEFAULT 0, cost_price DECIMAL(12,2) NOT NULL DEFAULT 0,"
            "buy_date DATE, alerts_enabled TINYINT(1) DEFAULT 1,"
            "risk_threshold INT DEFAULT 7,"
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
            "UNIQUE KEY uk_code (code)) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

            "CREATE TABLE IF NOT EXISTS risk_alerts ("
                "id INT AUTO_INCREMENT PRIMARY KEY,"
            "stock_code VARCHAR(10) NOT NULL, stock_name VARCHAR(50) NOT NULL,"
            "risk_level VARCHAR(10) NOT NULL, risk_score INT NOT NULL,"
            "risk_detail TEXT, suggestion TEXT, notified TINYINT(1) DEFAULT 0,"
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "INDEX idx_created (created_at), INDEX idx_stock (stock_code)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

            "CREATE TABLE IF NOT EXISTS settings ("
                "id INT AUTO_INCREMENT PRIMARY KEY,"
            "setting_key VARCHAR(100) NOT NULL UNIQUE, setting_value TEXT,"
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

            "CREATE TABLE IF NOT EXISTS analysis_history ("
                "id INT AUTO_INCREMENT PRIMARY KEY,"
            "stock_code VARCHAR(10), stock_name VARCHAR(50),"
            "analysis_type VARCHAR(50), analysis_result LONGTEXT,"
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "INDEX idx_type_created (analysis_type, created_at)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

            "CREATE TABLE IF NOT EXISTS daily_quotes ("
                "id INT AUTO_INCREMENT PRIMARY KEY,"
            "code VARCHAR(10) NOT NULL, trade_date DATE NOT NULL,"
            "open DECIMAL(10,2), high DECIMAL(10,2), low DECIMAL(10,2),"
            "close DECIMAL(10,2), volume BIGINT, amount DECIMAL(16,2),"
            "amplitude DECIMAL(10,2), pct_chg DECIMAL(10,2), turnover DECIMAL(10,2),"
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "UNIQUE KEY uk_code_date (code, trade_date)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

            "CREATE TABLE IF NOT EXISTS data_cache ("
            "cache_key VARCHAR(255) NOT NULL PRIMARY KEY,"
            "data_blob LONGBLOB NOT NULL,"
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "expires_at DATETIME,"
            "INDEX idx_expires (expires_at)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

            "CREATE TABLE IF NOT EXISTS sentiment_daily ("
            "id INT AUTO_INCREMENT PRIMARY KEY,"
            "code VARCHAR(10) NOT NULL, trade_date DATE NOT NULL,"
            "avg_score DECIMAL(10,4), pos_ratio DECIMAL(10,4), neg_ratio DECIMAL(10,4),"
            "news_count INT DEFAULT 0,"
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "UNIQUE KEY uk_code_date (code, trade_date)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

            "CREATE TABLE IF NOT EXISTS raw_news ("
            "id INT AUTO_INCREMENT PRIMARY KEY,"
            "code VARCHAR(10) NOT NULL, title VARCHAR(500) NOT NULL,"
            "url VARCHAR(500), date VARCHAR(20), source VARCHAR(50),"
            "hash VARCHAR(12), collected_at DATETIME,"
            "INDEX idx_code_date (code, date)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

            "CREATE TABLE IF NOT EXISTS stock_sectors ("
            "id INT AUTO_INCREMENT PRIMARY KEY,"
            "code VARCHAR(10) NOT NULL, sector_name VARCHAR(100) NOT NULL,"
            "UNIQUE KEY uk_code_sector (code, sector_name)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

            "CREATE TABLE IF NOT EXISTS backtest_results ("
            "id VARCHAR(64) PRIMARY KEY,"
            "strategy_name VARCHAR(100), stock_code VARCHAR(10),"
            "params JSON, metrics JSON, trades LONGTEXT, equity_curve LONGTEXT,"
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

            "CREATE TABLE IF NOT EXISTS scan_results ("
            "id INT AUTO_INCREMENT PRIMARY KEY,"
            "stock_code VARCHAR(10), stock_name VARCHAR(50),"
            "price DECIMAL(12,2), pct_chg DECIMAL(10,2),"
            "ai_risk_score INT, risk_level VARCHAR(10),"
            "reason TEXT, created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "INDEX idx_created (created_at)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

            "CREATE TABLE IF NOT EXISTS orders ("
            "id VARCHAR(32) PRIMARY KEY,"
            "symbol VARCHAR(10) NOT NULL, name VARCHAR(50) NOT NULL,"
            "side VARCHAR(5) NOT NULL, quantity INT NOT NULL DEFAULT 0,"
            "price_type VARCHAR(10) NOT NULL DEFAULT 'market',"
            "price DECIMAL(12,3) NOT NULL DEFAULT 0,"
            "filled_qty INT DEFAULT 0, filled_price DECIMAL(12,3) DEFAULT 0,"
            "status VARCHAR(20) NOT NULL DEFAULT 'pending',"
            "created_at DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,"
            "INDEX idx_symbol (symbol), INDEX idx_status (status)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

            "CREATE TABLE IF NOT EXISTS trades ("
            "id VARCHAR(32) PRIMARY KEY,"
            "order_id VARCHAR(32) NOT NULL,"
            "symbol VARCHAR(10) NOT NULL, name VARCHAR(50) NOT NULL,"
            "side VARCHAR(5) NOT NULL,"
            "price DECIMAL(12,3) NOT NULL, quantity INT NOT NULL,"
            "amount DECIMAL(16,2) NOT NULL,"
            "commission DECIMAL(10,2) DEFAULT 0,"
            "stamp_duty DECIMAL(10,2) DEFAULT 0,"
            "trade_time DATETIME DEFAULT CURRENT_TIMESTAMP,"
            "INDEX idx_symbol (symbol), INDEX idx_order (order_id)"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",

            "CREATE TABLE IF NOT EXISTS accounts ("
            "id VARCHAR(32) PRIMARY KEY,"
            "cash DECIMAL(16,2) NOT NULL DEFAULT 0,"
            "frozen DECIMAL(16,2) NOT NULL DEFAULT 0,"
            "market_value DECIMAL(16,2) NOT NULL DEFAULT 0,"
            "total_assets DECIMAL(16,2) NOT NULL DEFAULT 0,"
            "updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP"
            ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4",
        ]
        for sql in sqls:
            cls.execute(sql)
        if cls._conn:
            cls._conn.close()
            cls._conn = None
class HoldingsRepo:
    @classmethod
    def add(cls, code, name, shares, cost_price, buy_date="", alerts_enabled=True, risk_threshold=7):
        if not buy_date:
            buy_date = datetime.now().strftime("%Y-%m-%d")
        return Database.execute(
            "INSERT INTO holdings (code,name,shares,cost_price,buy_date,alerts_enabled,risk_threshold) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s) "
            "ON DUPLICATE KEY UPDATE name=VALUES(name),shares=VALUES(shares),"
            "cost_price=VALUES(cost_price),buy_date=VALUES(buy_date)",
            (code, name, shares, cost_price, buy_date, 1 if alerts_enabled else 0, risk_threshold),
        )
    @classmethod
    def get_all(cls):
        return Database.fetchall("SELECT * FROM holdings ORDER BY code")
    @classmethod
    def get_by_code(cls, code):
        return Database.fetchone("SELECT * FROM holdings WHERE code=%s", (code,))
    @classmethod
    def update(cls, code, **kwargs):
        allowed = {"name","shares","cost_price","buy_date","alerts_enabled","risk_threshold"}
        updates = {k:v for k,v in kwargs.items() if k in allowed}
        if not updates: return
        set_clause = ", ".join(f"{k}=%s" for k in updates)
        Database.execute(f"UPDATE holdings SET {set_clause} WHERE code=%s",
            tuple(updates.values()) + (code,))
    @classmethod
    def delete(cls, code):
        Database.execute("DELETE FROM holdings WHERE code=%s", (code,))
    @classmethod
    def count(cls):
        r = Database.fetchone("SELECT COUNT(*) as cnt FROM holdings")
        return r["cnt"] if r else 0

class RiskAlertRepo:
    @classmethod
    def add(cls, stock_code, stock_name, risk_level, risk_score, risk_detail="", suggestion=""):
        return Database.execute(
            "INSERT INTO risk_alerts (stock_code,stock_name,risk_level,risk_score,risk_detail,suggestion) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (stock_code, stock_name, risk_level, risk_score, risk_detail, suggestion),
        )
    @classmethod
    def get_recent(cls, limit=50):
        return Database.fetchall("SELECT * FROM risk_alerts ORDER BY created_at DESC LIMIT %s", (limit,))
    @classmethod
    def get_by_stock(cls, code, limit=20):
        return Database.fetchall("SELECT * FROM risk_alerts WHERE stock_code=%s ORDER BY created_at DESC LIMIT %s",
            (code, limit))
    @classmethod
    def get_unnotified(cls):
        return Database.fetchall("SELECT * FROM risk_alerts WHERE notified=0 ORDER BY risk_score DESC")
    @classmethod
    def mark_notified(cls, alert_id):
        Database.execute("UPDATE risk_alerts SET notified=1 WHERE id=%s", (alert_id,))

class SettingsRepo:
    @classmethod
    def get(cls, key, default=None):
        r = Database.fetchone("SELECT setting_value FROM settings WHERE setting_key=%s", (key,))
        if r:
            try: return json.loads(r["setting_value"])
            except Exception: return r["setting_value"]
        return default
    @classmethod
    def set(cls, key, value):
        val = json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value
        Database.execute("INSERT INTO settings (setting_key,setting_value) VALUES (%s,%s) "
            "ON DUPLICATE KEY UPDATE setting_value=VALUES(setting_value)", (key, val))
    @classmethod
    def get_all(cls):
        rows = Database.fetchall("SELECT setting_key,setting_value FROM settings")
        return {r["setting_key"]: r["setting_value"] for r in rows}

class DailyQuotesRepo:
    @classmethod
    def save_batch(cls, code, df):
        if df is None or df.empty:
            return
        import pandas as pd
        rows = []
        for _, row in df.iterrows():
            d = row.get("date")
            if hasattr(d, "strftime"):
                d = d.strftime("%Y-%m-%d")
            elif d is None:
                continue
            rows.append((
                code, d,
                float(row.get("open", 0)) if row.get("open") and not pd.isna(row.get("open")) else None,
                float(row.get("high", 0)) if row.get("high") and not pd.isna(row.get("high")) else None,
                float(row.get("low", 0)) if row.get("low") and not pd.isna(row.get("low")) else None,
                float(row.get("close", 0)) if row.get("close") and not pd.isna(row.get("close")) else None,
                int(row.get("volume", 0)) if row.get("volume") and not pd.isna(row.get("volume")) else None,
                float(row.get("amount", 0)) if row.get("amount") and not pd.isna(row.get("amount")) else None,
                float(row.get("amplitude", 0)) if row.get("amplitude") and not pd.isna(row.get("amplitude")) else None,
                float(row.get("pct_chg", 0)) if row.get("pct_chg") and not pd.isna(row.get("pct_chg")) else None,
                float(row.get("turnover", 0)) if row.get("turnover") and not pd.isna(row.get("turnover")) else None,
            ))
        if not rows:
            return
        conn = Database.get_connection()
        with conn.cursor() as cur:
            cur.executemany(
                "INSERT INTO daily_quotes (code,trade_date,open,high,low,close,volume,"
                "amount,amplitude,pct_chg,turnover) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE open=VALUES(open),high=VALUES(high),"
                "low=VALUES(low),close=VALUES(close),volume=VALUES(volume),"
                "amount=VALUES(amount),amplitude=VALUES(amplitude),"
                "pct_chg=VALUES(pct_chg),turnover=VALUES(turnover)",
                rows,
            )
            conn.commit()
    @classmethod
    def get_range(cls, code, start_date, end_date):
        rows = Database.fetchall(
            "SELECT * FROM daily_quotes WHERE code=%s AND trade_date>=%s AND trade_date<=%s "
            "ORDER BY trade_date", (code, start_date, end_date))
        if not rows:
            return None
        import pandas as pd
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["trade_date"])
        return df
    @classmethod
    def cleanup_old(cls, days=3):
        from datetime import datetime, timedelta
        cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
        Database.execute("DELETE FROM daily_quotes WHERE trade_date<%s", (cutoff,))
    @classmethod
    def has_data(cls, code, start_date, end_date):
        r = Database.fetchone(
            "SELECT COUNT(*) as cnt FROM daily_quotes WHERE code=%s AND trade_date>=%s AND trade_date<=%s",
            (code, start_date, end_date))
        return r and r["cnt"] > 0

class DataCacheRepo:
    """通用数据缓存 - 存到MySQL用于API失败时回退"""
    @classmethod
    def save(cls, key, data, expires_at=None):
        import pickle
        blob = pickle.dumps(data)
        Database.execute(
            "INSERT INTO data_cache (cache_key, data_blob, expires_at) VALUES (%s, %s, %s) "
            "ON DUPLICATE KEY UPDATE data_blob=VALUES(data_blob), expires_at=VALUES(expires_at)",
            (key, blob, expires_at))
    @classmethod
    def get(cls, key):
        import pickle
        from datetime import datetime
        row = Database.fetchone(
            "SELECT data_blob, expires_at FROM data_cache WHERE cache_key=%s", (key,))
        if not row:
            return None
        if row["expires_at"] and row["expires_at"] < datetime.now():
            return None
        return pickle.loads(row["data_blob"])

    @classmethod
    def cleanup_old(cls, days=3):
        """删除超过指定天数的缓存数据"""
        from datetime import datetime, timedelta
        cutoff = datetime.now() - timedelta(days=days)
        Database.execute("DELETE FROM data_cache WHERE created_at < %s", (cutoff,))

class AnalysisHistoryRepo:
    @classmethod
    def add(cls, stock_code, stock_name, analysis_type, result):
        return Database.execute(
            "INSERT INTO analysis_history (stock_code,stock_name,analysis_type,analysis_result) "
            "VALUES (%s,%s,%s,%s)", (stock_code, stock_name, analysis_type, result))
    @classmethod
    def get_recent(cls, limit=20):
        return Database.fetchall("SELECT * FROM analysis_history ORDER BY created_at DESC LIMIT %s", (limit,))
def execute_sql(sql, params=()):
    """便捷函数：执行SQL"""
    return Database.execute(sql, params)


def query_sql(sql, params=()):
    """便捷函数：查询SQL"""
    return Database.fetchall(sql, params)


