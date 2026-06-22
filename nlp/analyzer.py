"""DeepSeek API 情绪分类器"""
import json
from datetime import datetime

class SentimentAnalyzer:
    def __init__(self):
        self.batch_size = 50
    def analyze(self, items):
        results = []
        for i in range(0, len(items), self.batch_size):
            batch = items[i:i+self.batch_size]
            results.extend(self._analyze_batch(batch))
        return results
    def _analyze_batch(self, items):
        titles = [it["title"] for it in items if it.get("title")]
        if not titles:
            return items
        try:
            from utils.llm_client import LLMClient
            llm = LLMClient()
            prompt = self._build_prompt(titles)
            resp = llm.chat([{"role":"system","content":"你是一个金融情绪分析专家。"},
                             {"role":"user","content":prompt}])
            scores = self._parse_response(resp)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"analyze_batch: {e}")
            scores = {}
        for item in items:
            t = item.get("title","")
            s = scores.get(t, {})
            item["sentiment"] = s.get("sentiment","neutral")
            item["sentiment_score"] = s.get("score",0)
            item["confidence"] = s.get("confidence",0.5)
            item["analyzed_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return items
    def _build_prompt(self, titles):
        lines = [f"{i+1}. {t}" for i, t in enumerate(titles)]
        return ("分析以下新闻标题的情绪倾向，返回JSON数组，每项包含sentiment(positive/negative/neutral),"
                "score(-1到1),confidence(0-1):\n" + "\n".join(lines))
    def _parse_response(self, resp):
        try:
            text = resp if isinstance(resp, str) else (resp.get("content","") if isinstance(resp,dict) else str(resp))
            if "[" in text:
                text = text[text.index("["):text.rindex("]")+1]
            return {item.get("title",""): item for item in json.loads(text)} if text.startswith("[") else {}
        except Exception:
            return {}
