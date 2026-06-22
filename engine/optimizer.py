"""参数优化器——网格搜索 + 遗传算法"""
import itertools
import random
from .backtest import BacktestEngine

class GridOptimizer:
    def __init__(self):
        pass
    def optimize(self, strategy_cls, param_grid, data_feed, stock_code, start_date, end_date, cash=1000000, commission=0.0003):
        names = list(param_grid.keys())
        values = list(param_grid.values())
        results = []
        for combo in itertools.product(*values):
            try:
                params = dict(zip(names, combo))
                engine = BacktestEngine(cash=cash, commission=commission)
                result = engine.run(strategy_cls, params, data_feed, f"opt_{stock_code}", stock_code, start_date, end_date)
                result["params"] = params
                results.append(result)
            except Exception as e:
                results.append({"params": dict(zip(names, combo)), "error": str(e)})
        return self._rank(results)
    def _rank(self, results):
        def score(r):
            m = r.get("metrics", {}); s = 0
            s += (m.get("sharpe",0) or 0) * 10
            s += (m.get("total_return",0) or 0) * 0.5
            s -= abs(m.get("max_drawdown",0) or 0) * 0.5
            s += (m.get("win_rate",0) or 0) * 0.1
            return s
        scored = [(score(r), r) for r in results if "error" not in r]
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored]

class GeneticOptimizer:
    def __init__(self, population=15, generations=8, mutation_rate=0.2):
        self.pop = population; self.gen = generations; self.mr = mutation_rate
    def optimize(self, strategy_cls, param_grid, data_feed, stock_code, start_date, end_date, cash=1000000, commission=0.0003):
        names = list(param_grid.keys())
        choices = [list(v) for v in param_grid.values()]
        pop = [[random.choice(c) for c in choices] for _ in range(self.pop)]
        best = None
        for _ in range(self.gen):
            results = []
            for ind in pop:
                params = dict(zip(names, ind))
                try:
                    engine = BacktestEngine(cash=cash, commission=commission)
                    r = engine.run(strategy_cls, params, data_feed, "gen", stock_code, start_date, end_date)
                    r["params"] = params; r["_fitness"] = self._fitness(r); results.append(r)
                except Exception:
                    results.append({"params": params, "_fitness": -999})
            results.sort(key=lambda x: x.get("_fitness",-999), reverse=True)
            if results: best = results[0]
            elite = [r["params"] for r in results[:max(2, self.pop//4)]]
            next_pop = [[elite[i][n] for n in names] for i in range(len(elite))]
            while len(next_pop) < self.pop:
                p1 = random.choice(elite); p2 = random.choice(elite)
                child = {n: p1[n] if random.random()<0.5 else p2[n] for n in names}
                for n in names:
                    if random.random() < self.mr:
                        child[n] = random.choice(choices[names.index(n)])
                next_pop.append([child[n] for n in names])
            pop = next_pop
        return best
    def _fitness(self, r):
        m = r.get("metrics",{}); s = (m.get("sharpe",0) or 0)*10 + (m.get("total_return",0) or 0)*0.5
        return s - abs(m.get("max_drawdown",0) or 0)*0.5 + (m.get("win_rate",0) or 0)*0.1
