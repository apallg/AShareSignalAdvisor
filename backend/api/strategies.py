"""策略文件管理 + AI 策略生成 API"""
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()

STRATEGIES_DIR = Path(__file__).parent.parent.parent / "strategies"
EDITABLE_DIRS = {"custom", "community"}


class FileContent(BaseModel):
    path: str  # "custom/xxx.py"
    code: str


class GenerateRequest(BaseModel):
    idea: str


def _safe_path(rel: str) -> Path:
    full = (STRATEGIES_DIR / rel).resolve()
    if not str(full).startswith(str(STRATEGIES_DIR.resolve())):
        raise HTTPException(403, "路径越界")
    return full


@router.get("/open-dir")
def get_strategies_dir_for_open():
    import os
    host_dir = os.environ.get("STRATEGIES_HOST_DIR", str(STRATEGIES_DIR.resolve()))
    return {"data": {"path": host_dir}}


@router.get("/open-dir-bat")
def download_open_bat():
    import os
    from fastapi.responses import PlainTextResponse
    from urllib.parse import quote
    host_dir = os.environ.get("STRATEGIES_HOST_DIR", str(STRATEGIES_DIR.resolve()))
    bat = f'@echo off\r\nstart "" "{host_dir}"\r\n'
    filename = "open_strategies_folder.bat"
    return PlainTextResponse(bat, media_type="application/x-bat", headers={
        "Content-Disposition": f"attachment; filename={filename}"
    })


@router.get("/files")
def list_strategy_files():
    files = []
    for subdir in ["classic", "hybrid", "custom", "community"]:
        d = STRATEGIES_DIR / subdir
        if not d.exists():
            continue
        for f in sorted(d.glob("*.py")):
            if f.name == "__init__.py":
                continue
            rel = f"{subdir}/{f.name}"
            files.append({
                "path": rel,
                "name": f.stem,
                "dir": subdir,
                "editable": subdir in EDITABLE_DIRS,
            })
    return {"data": files}


@router.get("/file")
def read_strategy_file(path: str):
    full = _safe_path(path)
    if not full.exists():
        raise HTTPException(404, "文件不存在")
    parts = Path(path).parts
    editable = parts[0] in EDITABLE_DIRS
    return {"data": {"path": path, "code": full.read_text(encoding="utf-8"), "editable": editable}}


@router.post("/file")
def save_strategy_file(req: FileContent):
    parts = Path(req.path).parts
    if parts[0] not in EDITABLE_DIRS:
        raise HTTPException(403, "只能编辑 custom/ 或 community/ 目录下的策略")
    full = _safe_path(req.path)
    full.parent.mkdir(parents=True, exist_ok=True)
    full.write_text(req.code, encoding="utf-8")
    try:
        from strategies.registry import auto_discover
        auto_discover()
    except Exception:
        pass
    try:
        from execution.live.strategies import reload_live_strategies
        reload_live_strategies()
    except Exception:
        pass
    return {"status": "ok"}


@router.delete("/file")
def delete_strategy_file(path: str):
    parts = Path(path).parts
    if parts[0] not in EDITABLE_DIRS:
        raise HTTPException(403, "只能删除 custom/ 或 community/ 目录下的策略")
    full = _safe_path(path)
    if full.exists():
        full.unlink()
    try:
        from strategies.registry import auto_discover
        auto_discover()
    except Exception:
        pass
    try:
        from execution.live.strategies import reload_live_strategies
        reload_live_strategies()
    except Exception:
        pass
    return {"status": "ok"}


@router.get("/template")
def get_template(name: str = "my_strategy"):
    code = f'''"""{name}"""
import backtrader as bt
from strategies.base import BaseStrategy


class {name.title().replace("_", "")}Strategy(BaseStrategy):
    params = (("fast", 5), ("slow", 20))

    def __init__(self):
        super().__init__()
        self.ma_fast = bt.indicators.SMA(self.data.close, period=self.p.fast)
        self.ma_slow = bt.indicators.SMA(self.data.close, period=self.p.slow)
        self.crossover = bt.indicators.CrossOver(self.ma_fast, self.ma_slow)

    def next(self):
        if self.crossover[0] == 1:
            self.buy_signal(reason=f"金叉({{self.p.fast}},{{self.p.slow}})")
        elif self.crossover[0] == -1:
            self.sell_signal(reason=f"死叉({{self.p.fast}},{{self.p.slow}})")
        if self.position and self.entry_price:
            pct = (self.data.close[0] - self.entry_price) / self.entry_price * 100
            if pct <= self.p.stop_loss:
                self.sell_signal(reason=f"止损({{pct:.1f}}%)")
            elif pct >= self.p.take_profit:
                self.sell_signal(reason=f"止盈({{pct:.1f}}%)")


# ---- 实盘版本 ----
import numpy as np
from execution.live.base import LiveStrategy


class Live{name.title().replace("_", "")}Strategy(LiveStrategy):
    name = "{name}"
    description = "自定义策略"
    params = {{"fast": 5, "slow": 20, "stop_loss": -8, "take_profit": 20}}

    def check_signal(self, df):
        if len(df) < self.slow + 1:
            return {{"action": "hold", "size_ratio": 0, "reason": ""}}
        close = df["close"].values
        fast_ma = df["close"].rolling(self.fast).mean().values
        slow_ma = df["close"].rolling(self.slow).mean().values
        curr_fast, prev_fast = fast_ma[-1], fast_ma[-2]
        curr_slow, prev_slow = slow_ma[-1], slow_ma[-2]
        price = close[-1]

        if self.position == 0:
            if prev_fast <= prev_slow and curr_fast > curr_slow:
                return {{"action": "buy", "size_ratio": 1.0, "reason": f"金叉(MA{{self.fast}}↑MA{{self.slow}})"}}
        else:
            pnl_pct = (price - self.entry_price) / self.entry_price * 100
            if pnl_pct <= self.stop_loss:
                return {{"action": "sell", "size_ratio": 1.0, "reason": f"止损({{pnl_pct:.1f}}%)"}}
            if pnl_pct >= self.take_profit:
                return {{"action": "sell", "size_ratio": 1.0, "reason": f"止盈({{pnl_pct:.1f}}%)"}}
            if prev_fast >= prev_slow and curr_fast < curr_slow:
                return {{"action": "sell", "size_ratio": 1.0, "reason": f"死叉(MA{{self.fast}}↓MA{{self.slow}})"}}
        return {{"action": "hold", "size_ratio": 0, "reason": ""}}
'''
    return {"data": {"code": code}}


def _clean_code(text):
    code = text.strip()
    if code.startswith("```"):
        lines = code.split("\n")
        if lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        code = "\n".join(lines)
    return code.strip()


@router.post("/generate")
def generate_strategy(req: GenerateRequest):
    from utils.llm_client import LLMClient
    from agents.prompts import STRATEGY_CODER_PROMPT, STRATEGY_CODE_REVIEWER_PROMPT, STRATEGY_LOGIC_REVIEWER_PROMPT

    llm = LLMClient()

    # 第1步：生成代码
    coder_msg = [
        {"role": "system", "content": STRATEGY_CODER_PROMPT},
        {"role": "user", "content": req.idea},
    ]
    try:
        raw = llm.chat(coder_msg, temperature=0.3, max_tokens=4096)
        code = _clean_code(raw)
    except Exception as e:
        raise HTTPException(500, f"代码生成失败: {e}")

    # 第2步：代码审查
    reviewer_msg = [
        {"role": "system", "content": STRATEGY_CODE_REVIEWER_PROMPT},
        {"role": "user", "content": f"用户需求：{req.idea}\n\n待审查代码：\n{code}"},
    ]
    try:
        code_review = llm.chat(reviewer_msg, temperature=0.3, max_tokens=2048)
    except Exception:
        code_review = "代码审查暂不可用"

    # 第3步：逻辑审查
    logic_msg = [
        {"role": "system", "content": STRATEGY_LOGIC_REVIEWER_PROMPT},
        {"role": "user", "content": f"用户需求：{req.idea}\n\n待评审策略代码：\n{code}"},
    ]
    try:
        logic_review = llm.chat(logic_msg, temperature=0.3, max_tokens=2048)
    except Exception:
        logic_review = "逻辑审查暂不可用"

    return {"data": {"code": code, "code_review": code_review, "logic_review": logic_review}}
