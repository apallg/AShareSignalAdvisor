"""5 Agent 辩论面板"""
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError
import logging
from utils.llm_client import LLMClient
from utils.cache_manager import CacheManager
from agents.prompts import (
    ANALYST_TECH_PROMPT, ANALYST_FUNDAMENTAL_PROMPT,
    ANALYST_CAPITAL_PROMPT, ANALYST_MACRO_PROMPT,
    ANALYST_RISK_PROMPT, MODERATOR_PROMPT,
)

logger = logging.getLogger(__name__)
AGENT_TIMEOUT = 60  # 单个 Agent 超时秒数

class _Agent:
    def __init__(self, name, role_prompt, llm, cache=None):
        self.name = name
        self.role = role_prompt
        self.llm = llm
        self.cache = cache
    def analyze(self, context, temperature=0.7):
        messages = [
            {"role": "system", "content": self.role},
            {"role": "user", "content": context},
        ]
        return self.llm.chat_with_cache(messages, temperature=temperature, cache_manager=self.cache)

class DebatePanel:
    def __init__(self, llm=None, cache=None):
        llm = llm or LLMClient()
        self.a = {
            "tech": _Agent("技术分析师", ANALYST_TECH_PROMPT, llm, cache),
            "fund": _Agent("基本面分析师", ANALYST_FUNDAMENTAL_PROMPT, llm, cache),
            "cap": _Agent("资金面分析师", ANALYST_CAPITAL_PROMPT, llm, cache),
            "macro": _Agent("宏观策略师", ANALYST_MACRO_PROMPT, llm, cache),
            "risk": _Agent("风控官", ANALYST_RISK_PROMPT, llm, cache),
            "mod": _Agent("主持人", MODERATOR_PROMPT, llm, cache),
        }
    def debate(self, stock_name, stock_code, data_context):
        header = f"股票名称: {stock_name}\n股票代码: {stock_code}\n\n=== 数据 ===\n{data_context}\n"

        agent_keys = ["tech", "fund", "cap", "macro"]
        results = {}
        with ThreadPoolExecutor(max_workers=4) as pool:
            futures = {pool.submit(self.a[k].analyze, header): k for k in agent_keys}
            for f in as_completed(futures, timeout=AGENT_TIMEOUT + 10):
                k = futures[f]
                try:
                    results[k] = f.result(timeout=AGENT_TIMEOUT)
                except (FuturesTimeoutError, TimeoutError):
                    logger.warning(f"Agent [{self.a[k].name}] 超时，使用降级输出")
                    results[k] = f"[{self.a[k].name}] 分析超时，请稍后重试"
                except Exception as e:
                    logger.error(f"Agent [{self.a[k].name}] 异常: {e}")
                    results[k] = f"[{self.a[k].name}] 分析失败: {e}"

        tech = results.get("tech", "")
        fund = results.get("fund", "")
        cap = results.get("cap", "")
        macro = results.get("macro", "")

        ctx = header
        ctx += f"\n\n[技术分析师]\n{tech}"
        ctx += f"\n\n[基本面分析师]\n{fund}"
        ctx += f"\n\n[资金面分析师]\n{cap}"
        ctx += f"\n\n[宏观策略师]\n{macro}"

        try:
            risk = self.a["risk"].analyze(ctx)
        except Exception as e:
            logger.error(f"风控官异常: {e}")
            risk = f"[风控官] 分析失败: {e}"
        ctx += f"\n\n[风控官]\n{risk}"

        try:
            final = self.a["mod"].analyze(ctx)
        except Exception as e:
            logger.error(f"主持人异常: {e}")
            final = f"[主持人] 分析失败: {e}"

        return {"技术分析": tech, "基本面分析": fund, "资金面分析": cap,
                "宏观分析": macro, "风险审查": risk, "最终决议": final}
