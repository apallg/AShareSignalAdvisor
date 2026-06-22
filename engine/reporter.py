"""回测结果序列化"""


def serialize_result(result):
    """转换为 JSON 安全字典"""
    return {
        'id': result.get('id', ''),
        'strategy': result.get('strategy_name', ''),
        'stock': result.get('stock_code', ''),
        'period': result.get('period', ''),
        'created_at': result.get('created_at', ''),
        'metrics': result.get('metrics', {}),
        'equity_curve': result.get('equity_curve', []),
        'trades': result.get('trades', []),
    }


def result_to_chart_data(result):
    """提取前端 ECharts 需要的格式"""
    curve = result.get('equity_curve', [])
    return {
        'dates': [p.get('date', '') for p in curve],
        'values': [p.get('value', 0) for p in curve],
    }


def result_to_trade_table(result):
    """提取前端交易记录表格"""
    return result.get('trades', [])
