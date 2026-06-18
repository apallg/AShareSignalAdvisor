"""持仓管理 + 风险扫描引擎"""
import logging
from typing import List, Dict, Optional
 
import config
from core.database import Database, HoldingsRepo, RiskAlertRepo
from core.data_fetcher import DataFetcher
from core.analyzer import Analyzer
from core.realtime import RealtimeEngine
from agents.panel import DebatePanel
from utils.cache_manager import CacheManager
from utils.llm_client import LLMClient
from utils.notifier import send_risk_alert, get_notifier
 
logger = logging.getLogger(__name__)
 
 
class PortfolioScanner:
    """扫描持仓, 逐个进行多Agent辩论 + 风险评分"""
 
    def __init__(self, debate_panel: Optional[DebatePanel] = None,
                 fetcher: Optional[DataFetcher] = None,
                 analyzer: Optional[Analyzer] = None):
        self.cache = CacheManager()
        self.fetcher = fetcher or DataFetcher(self.cache)
        self.analyzer = analyzer or Analyzer()
        self.realtime = RealtimeEngine()
        llm = LLMClient()
        self.panel = debate_panel or DebatePanel(llm=llm, cache=self.cache)
 
    def scan_holding(self, holding: Dict, include: Optional[Dict[str, bool]] = None) -> Optional[Dict]:
        """扫描单只持仓，返回风险评估结果"""
        # 数据源勾选配置：默认全部启用
        inc = {"daily": True, "technical": True, "financial": True, "realtime": True, "patterns": True}
        if include:
            inc.update(include)
        code = holding["code"]
        name = holding["name"]
        shares = holding["shares"]
        cost_price = float(holding["cost_price"])

        logger.info(f"扫描持仓: {name}({code}) inc={inc}")
        enabled = []
        skipped = []

        # ─── 日K线（必须） ───────────────────
        if not inc.get("daily", True):
            raise ValueError("日K线不能禁用")
        try:
            df = self.fetcher.get_stock_daily(code)
        except Exception as e:
            raise ValueError(f"日K线获取失败: {e}")
        if df is None or df.empty:
            raise ValueError("日K线数据为空")
        enabled.append("日K线")

        # ─── 技术指标 ────────────────────────
        sig = []
        if inc.get("technical", True):
            try:
                df = self.analyzer.add_indicators(df)
                sig = self.analyzer.detect_cross_signals(df) or []
            except Exception as e:
                raise ValueError(f"技术指标计算失败: {e}")
            enabled.append("技术指标")
        else:
            skipped.append("技术指标")

        # ─── 财务指标 ────────────────────────
        financial = None
        if inc.get("financial", True):
            financial = self.fetcher.get_stock_financial(code)
            if not financial:
                raise ValueError("财务指标获取失败")
            enabled.append("财务指标")
        else:
            skipped.append("财务指标")

        # ─── 实时行情 ────────────────────────
        quote = None
        if inc.get("realtime", True):
            quote = self.realtime.get_realtime_price(code)
            if not quote:
                quote = self.fetcher.get_realtime_quote(code)
            if not quote:
                raise ValueError("实时行情获取失败")
            enabled.append("实时行情")
        else:
            skipped.append("实时行情")

        # ─── K线形态 ─────────────────────────
        patterns = []
        if inc.get("patterns", True):
            try:
                pat = self.analyzer.detect_kline_patterns(df)
                patterns = pat or []
            except Exception as e:
                raise ValueError(f"K线形态识别失败: {e}")
            enabled.append("K线形态")
        else:
            skipped.append("K线形态")

        # ─── 构建上下文 ─────────────────────
        # 指标已在上面通过 add_indicators 添加，跳过重复计算
        data_context = self.analyzer.get_analysis_context(df, financial or {}, indicators_added=True)
        data_context += f"\n\n股票名称: {name}\n股票代码: {code}"
        data_context += f"\n启用数据源: {', '.join(enabled)}"
        if skipped:
            data_context += f"\n未启用数据源: {', '.join(skipped)}"
        if quote:
            pct = quote.get("pct_chg", quote.get("涨跌幅", 0))
            price = quote.get("price", quote.get("最新价", 0))
            data_context += f"\n实时价格: {price}\n实时涨跌幅: {pct}%\n"
        if sig:
            data_context += "\n技术交叉信号:\n"
            for t, d in sig:
                data_context += f"- {t}: {d}\n"
        if patterns:
            data_context += "\nK线形态:\n"
            for pn, pd in patterns[:5]:
                data_context += f"- {pn}: {pd}\n"

        # ─── 多 Agent 辩论 ─────────────────
        try:
            debate_result = self.panel.debate(name, code, data_context)
            final = debate_result.get("最终决议", "")
        except Exception as e:
            logger.error(f"辩论失败: {e}")
            return None
 
        # 从最终决议中提取风险等级和评分
        risk_level, risk_score = self._parse_risk(final)

        current_price = float(quote.get("price", quote.get("最新价", 0))) if quote else 0
        profit_loss = 0
        profit_loss_pct = 0
        if current_price and cost_price:
            profit_loss = (current_price - cost_price) * shares
            profit_loss_pct = (current_price - cost_price) / cost_price * 100
 
        result = {
            "stock_code": code,
            "stock_name": name,
            "shares": shares,
            "cost_price": cost_price,
            "current_price": current_price,
            "profit_loss": round(profit_loss, 2),
            "profit_loss_pct": round(profit_loss_pct, 2),
            "risk_level": risk_level,
            "risk_score": risk_score,
            "risk_detail": final,
            "suggestion": self._extract_suggestion(final),
            "debate_result": debate_result,
            "data_enabled": enabled,
            "data_skipped": skipped,
        }
        return result
 
    def scan_all(self, threshold: int = 5, include: Optional[Dict[str, bool]] = None) -> List[Dict]:
        """扫描所有持仓, 返回风险列表(仅风险≥threshold)"""
        holdings = HoldingsRepo.get_all()
        if not holdings:
            logger.info("无持仓记录")
            return []
 
        alerts = []
        for h in holdings:
            if not h.get("alerts_enabled", True):
                continue
            result = self.scan_holding(h, include=include)
            if result and result["risk_score"] >= threshold:
                alerts.append(result)
                # 持久化告警记录
                self._persist_alert(result)
                # Coze 通知推送
                self._notify_if_needed(result, h)
        return alerts
 
    def _parse_risk(self, text: str):
        """从最终决议中解析风险等级和评分"""
        import re
        level = "低风险"
        score = 0
        # 优先匹配固定格式区块
        block = re.search(r"风险评分:\s*(\d+)/10\s*\n\s*风险等级:\s*(高风险|中风险|低风险)", text)
        if block:
            score = int(block.group(1))
            level = block.group(2)
            return level, score

        # 回退匹配自由格式
        m = re.search(r"风险评分[：:]\s*(\d+)(?:/10)?", text)
        if m:
            score = int(m.group(1))
            if score >= 7:
                level = "高风险"
            elif score >= 5:
                level = "中风险"
            return level, score

        # 尝试匹配风险等级关键词
        if "高风险" in text and level != "高风险":
            level = "高风险"
            if score < 7:
                score = max(score, 7)
        elif "中风险" in text and level == "低风险":
            level = "中风险"
            if score < 5:
                score = max(score, 5)

        return level, score
 
    def _extract_suggestion(self, text: str) -> str:
        """从最终决议中提取建议部分"""
        import re
        m = re.search(r"(?:建议|操作建议|投资建议)[：:](.*?)(?:\n\n|\Z)", text, re.DOTALL)
        if m:
            return m.group(1).strip()
        return ""
 
    def _persist_alert(self, result: Dict):
        """保存告警记录到数据库"""
        try:
            if not Database.is_available():
                return
            RiskAlertRepo.add(
                stock_code=result["stock_code"],
                stock_name=result["stock_name"],
                risk_level=result["risk_level"],
                risk_score=result["risk_score"],
                risk_detail=result["risk_detail"][:2000],
                suggestion=result["suggestion"][:500],
            )
        except Exception as e:
            logger.error(f"告警持久化失败: {e}")
 
    def _notify_if_needed(self, result: Dict, holding: Dict):
        """高风险/中风险推送 Coze 通知"""
        threshold = holding.get("risk_threshold", 7)
        if result["risk_score"] >= threshold:
            logger.info(f"触发告警推送: {result['stock_name']} 风险{result['risk_score']}分")
            try:
                send_risk_alert(
                    stock_name=result["stock_name"],
                    stock_code=result["stock_code"],
                    risk_level=result["risk_level"],
                    risk_score=result["risk_score"],
                    risk_detail=result["risk_detail"][:1000],
                    suggestion=result["suggestion"],
                    shares=result["shares"],
                    cost_price=result["cost_price"],
                )
            except Exception as e:
                logger.error(f"Coze 通知失败: {e}")
