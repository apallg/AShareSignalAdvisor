"""
MySQL daily_quotes → qlib 二进制格式 数据桥接
"""
import os
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from qlib_integration.utils import mysql_to_qlib_code

logger = logging.getLogger(__name__)

FIELDS = ["open", "high", "low", "close", "volume", "amount", "vwap"]


class QlibDataBridge:
    def __init__(self, data_dir):
        self.data_dir = Path(data_dir)
        self.calendar_dir = self.data_dir / "calendars"
        self.instruments_dir = self.data_dir / "instruments"
        self.features_dir = self.data_dir / "features"
        for d in [self.calendar_dir, self.instruments_dir, self.features_dir]:
            d.mkdir(parents=True, exist_ok=True)

    def sync_all(self):
        from core.database import Database

        conn = Database.get_connection()
        cursor = conn.cursor()

        # 1. 生成日历
        cursor.execute("SELECT DISTINCT trade_date FROM daily_quotes ORDER BY trade_date")
        dates = [row["trade_date"] for row in cursor.fetchall()]
        if not dates:
            raise RuntimeError("MySQL daily_quotes 表为空，请先采集数据")
        calendar_path = self.calendar_dir / "day.txt"
        with open(calendar_path, "w", encoding="utf-8") as f:
            for d in dates:
                d_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
                f.write(d_str + "\n")
        date_to_idx = {str(d): i for i, d in enumerate(dates)}

        # 2. 生成 instruments
        cursor.execute(
            "SELECT code, MIN(trade_date) as start, MAX(trade_date) as end "
            "FROM daily_quotes GROUP BY code ORDER BY code"
        )
        instruments_rows = cursor.fetchall()
        inst_path = self.instruments_dir / "all.txt"
        with open(inst_path, "w", encoding="utf-8") as f:
            for row in instruments_rows:
                qlib_code = mysql_to_qlib_code(row["code"])
                start_str = row["start"].strftime("%Y-%m-%d") if hasattr(row["start"], "strftime") else str(row["start"])
                end_str = row["end"].strftime("%Y-%m-%d") if hasattr(row["end"], "strftime") else str(row["end"])
                f.write(f"{qlib_code}\t{start_str}\t{end_str}\n")

        # 3. 生成 features 目录
        total_calendar_len = len(dates)
        n_total = len(instruments_rows)

        # 批量查询优化：一次获取所有数据
        cursor.execute("SELECT code, trade_date, open, high, low, close, volume, amount "
                        "FROM daily_quotes ORDER BY trade_date")
        all_rows = cursor.fetchall()

        # 按 code 分组
        code_data = {}
        for row in all_rows:
            code = row["code"]
            if code not in code_data:
                code_data[code] = {"dates": [], "values": {f: [] for f in FIELDS}}
            d = row["trade_date"]
            d_str = d.strftime("%Y-%m-%d") if hasattr(d, "strftime") else str(d)
            idx = date_to_idx.get(d_str)
            if idx is None:
                continue
            code_data[code]["dates"].append(idx)
            code_data[code]["values"]["open"].append(float(row["open"]) if row["open"] is not None else np.nan)
            code_data[code]["values"]["high"].append(float(row["high"]) if row["high"] is not None else np.nan)
            code_data[code]["values"]["low"].append(float(row["low"]) if row["low"] is not None else np.nan)
            code_data[code]["values"]["close"].append(float(row["close"]) if row["close"] is not None else np.nan)
            code_data[code]["values"]["volume"].append(float(row["volume"]) if row["volume"] is not None else np.nan)
            code_data[code]["values"]["amount"].append(float(row["amount"]) if row["amount"] is not None else np.nan)

        # 计算 vwap
        n_done = 0
        for mysql_code, data in code_data.items():
            qlib_code = mysql_to_qlib_code(mysql_code)
            dates_arr = np.array(data["dates"])
            stock_dir = self.features_dir / qlib_code.lower()
            stock_dir.mkdir(parents=True, exist_ok=True)

            for field in FIELDS:
                if field == "vwap":
                    amount_arr = np.array(data["values"]["amount"], dtype=np.float64)
                    volume_arr = np.array(data["values"]["volume"], dtype=np.float64)
                    vwap_vals = np.where(volume_arr > 0, amount_arr / volume_arr, np.nan)
                    values_arr = vwap_vals.astype(np.float64)
                else:
                    values_arr = np.array(data["values"][field], dtype=np.float64)

                # 对齐到全局日历
                start_idx = int(dates_arr[0])
                end_idx = int(dates_arr[-1])
                full = np.full(end_idx - start_idx + 1, np.nan, dtype=np.float64)
                for i, idx in enumerate(dates_arr):
                    pos = int(idx) - start_idx
                    full[pos] = values_arr[i]

                # 写入二进制文件
                bin_path = stock_dir / f"{field}.day.bin"
                np.hstack([np.float32(start_idx), full.astype(np.float32)]).astype("<f").tofile(str(bin_path))

            n_done += 1
            if n_done % 500 == 0:
                logger.info(f"  数据桥接进度: {n_done}/{len(code_data)}")

        cursor.close()
        logger.info(f"数据桥接完成: {len(dates)} 个交易日, {n_total} 只股票")
        return {"dates": len(dates), "stocks": n_total, "data_dir": str(self.data_dir)}

    def get_status(self):
        """返回当前 qlib 数据状态"""
        cal_path = self.calendar_dir / "day.txt"
        inst_path = self.instruments_dir / "all.txt"
        if not cal_path.exists() or not inst_path.exists():
            return {"synced": False, "dates": 0, "stocks": 0}

        dates = cal_path.read_text().strip().splitlines()
        stocks = inst_path.read_text().strip().splitlines()
        first_date = dates[0] if dates else None
        last_date = dates[-1] if dates else None
        return {
            "synced": True,
            "dates": len(dates),
            "stocks": len(stocks),
            "first_date": first_date,
            "last_date": last_date,
        }
