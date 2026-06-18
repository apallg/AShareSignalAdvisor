"""5 Agent 辩论面板"""
from typing import Optional
from utils.llm_client import LLMClient
from utils.cache_manager import CacheManager
from agents.prompts import (
    ANALYST_TECH_PROMPT, ANALYST_FUNDAMENTAL_PROMPT,
    ANALYST_CAPITAL_PROMPT, ANALYST_MACRO_PROMPT,
    ANALYST_RISK_PROMPT, MODERATOR_PROMPT,
)

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
        tech = self.a["tech"].analyze(header)
        fund = self.a["fund"].analyze(header)
        cap = self.a["cap"].analyze(header)
        macro = self.a["macro"].analyze(header)
        ctx = header
        ctx += "\n\n[技术分析师]\n" + tech
        ctx += "\n\n[基本面分析师]\n" + fund
        ctx += "\n\n[资金面分析师]\n" + cap
        ctx += "\n\n[宏观策略师]\n" + macro
        risk = self.a["risk"].analyze(ctx)
        ctx += "\n\n[风控官]\n" + risk
        final = self.a["mod"].analyze(ctx)
        return {"技术分析": tech, "基本面分析": fund, "资金面分析": cap,
                "宏观分析": macro, "风险审查": risk, "最终决议": final}
