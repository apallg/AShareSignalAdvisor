"""绩效指标计算"""
from datetime import datetime
import math


def calculate_metrics(strat, cerebro, strategy_id, stock_code, 
                      start_date, end_date):
    """从 backtrader 分析器中提取绩效指标"""
    sharpe_ana = strat.analyzers.sharpe.get_analysis()
    drawdown_ana = strat.analyzers.drawdown.get_analysis()
    returns_ana = strat.analyzers.returns.get_analysis()
    trades_ana = strat.analyzers.trades.get_analysis()
    
    sharpe_ratio = sharpe_ana.get('sharperatio', None)
    max_dd = drawdown_ana.get('max', {}).get('drawdown', 0)
    total_return = returns_ana.get('rtot', 0) * 100
    annual_return = returns_ana.get('rnorm100', None)
    
    t = trades_ana.get('total', {})
    trade_count = t.get('total', 0)
    won = trades_ana.get('won', {}).get('total', 0)
    lost = trades_ana.get('lost', {}).get('total', 0)
    win_rate = (won / trade_count * 100) if trade_count > 0 else 0
    
    pnl_won = abs(trades_ana.get('pnl', {}).get('won', {}).get('total', 0))
    pnl_lost = abs(trades_ana.get('pnl', {}).get('lost', {}).get('total', 0))
    pl_ratio = round(pnl_won / pnl_lost, 2) if pnl_lost != 0 else None
    
    equity_curve = getattr(strat, 'equity_curve', [])
    trade_log = getattr(strat, 'trade_log', [])
    
    result = {
        'id': strategy_id or f"bt_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
        'stock_code': stock_code,
        'strategy_name': strategy_cls_name(strat),
        'period': f"{start_date} ~ {end_date}",
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        'metrics': {
            'total_return': round(total_return, 2),
            'annual_return': round(annual_return, 2) if annual_return else None,
            'sharpe': round(sharpe_ratio, 2) if sharpe_ratio else None,
            'max_drawdown': round(max_dd, 2) if max_dd else 0,
            'win_rate': round(win_rate, 1),
            'profit_loss_ratio': pl_ratio,
            'total_trades': trade_count,
        },
        'equity_curve': equity_curve,
        'trades': trade_log,
    }
    return result


def strategy_cls_name(strat):
    try:
        return type(strat).__name__
    except Exception:
        return ""
