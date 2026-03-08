"""
NoFOMO - 股票交易記錄與點位建議系統
"""

import os
import json
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional

# Data directory
DATA_DIR = Path(__file__).parent.parent / 'data'
TRADES_DIR = DATA_DIR / 'trades'
PORTFOLIO_FILE = DATA_DIR / 'portfolio.json'

DATA_DIR.mkdir(parents=True, exist_ok=True)
TRADES_DIR.mkdir(parents=True, exist_ok=True)


def get_trades() -> List[Dict]:
    """取得所有交易記錄"""
    trades = []
    for f in TRADES_DIR.glob('*.json'):
        with open(f, 'r', encoding='utf-8') as fp:
            trades.append(json.load(fp))
    return sorted(trades, key=lambda x: x.get('date', ''), reverse=True)


def get_portfolio() -> Dict:
    """取得目前持倉"""
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as fp:
            return json.load(fp)
    return {'positions': [], 'cash': 0, 'total_value': 0}


def save_portfolio(portfolio: Dict):
    """儲存持倉"""
    with open(PORTFOLIO_FILE, 'w', encoding='utf-8') as fp:
        json.dump(portfolio, fp, ensure_ascii=False, indent=2)


def add_trade(trade: Dict) -> str:
    """新增交易記錄"""
    trade_id = datetime.now().strftime('%Y%m%d_%H%M%S_%f')  # 含微秒，避免同秒衝突
    trade['id'] = trade_id
    trade['created_at'] = datetime.now().isoformat()
    
    filepath = TRADES_DIR / f"{trade_id}.json"
    with open(filepath, 'w', encoding='utf-8') as fp:
        json.dump(trade, fp, ensure_ascii=False, indent=2)
    
    # 更新持倉
    update_portfolio(trade)
    
    return trade_id


def update_portfolio(trade: Dict):
    """更新持倉狀態"""
    portfolio = get_portfolio()
    
    ticker = trade.get('ticker', '').upper()
    action = trade.get('action', '').upper()
    quantity = float(trade.get('quantity', 0))
    price = float(trade.get('entry_price', 0))
    
    # 找尋現有部位
    position = None
    for p in portfolio.get('positions', []):
        if p.get('ticker') == ticker:
            position = p
            break
    
    if action == 'BUY':
        if position:
            # 加碼
            total_qty = position.get('quantity', 0) + quantity
            avg_price = ((position.get('quantity', 0) * position.get('avg_price', 0)) + (quantity * price)) / total_qty
            position['quantity'] = total_qty
            position['avg_price'] = avg_price
        else:
            # 新建部位
            portfolio.setdefault('positions', []).append({
                'ticker': ticker,
                'quantity': quantity,
                'avg_price': price,
                'entry_date': trade.get('date')
            })
    
    elif action == 'SELL' and position:
        position['quantity'] -= quantity
        if position['quantity'] <= 0:
            portfolio['positions'] = [p for p in portfolio.get('positions', []) if p.get('ticker') != ticker]
    
    save_portfolio(portfolio)


def calculate_pnl() -> Dict:
    """計算已實現損益（依平均成本法計算賣出損益）"""
    trades = get_trades()
    # 依時間正序還原部位
    trades_sorted = sorted(
        trades,
        key=lambda x: x.get('date', '') or x.get('created_at', '')
    )

    positions: Dict[str, Dict] = {}
    realized_pnl = 0.0

    for trade in trades_sorted:
        ticker = trade.get('ticker', '').upper()
        action = trade.get('action', '').upper()
        quantity = float(trade.get('quantity', 0))
        price = float(trade.get('entry_price', 0))

        if ticker not in positions:
            positions[ticker] = {'quantity': 0.0, 'avg_price': 0.0}

        if action == 'BUY':
            old_qty = positions[ticker]['quantity']
            old_avg = positions[ticker]['avg_price']
            new_qty = old_qty + quantity
            positions[ticker]['avg_price'] = (
                (old_qty * old_avg + quantity * price) / new_qty
                if new_qty > 0 else 0.0
            )
            positions[ticker]['quantity'] = new_qty

        elif action == 'SELL' and positions[ticker]['quantity'] > 0:
            cost_basis = positions[ticker]['avg_price']
            sell_qty = min(quantity, positions[ticker]['quantity'])
            realized_pnl += (price - cost_basis) * sell_qty
            positions[ticker]['quantity'] -= sell_qty

    return {
        'realized_pnl': round(realized_pnl, 2),
        'unrealized_pnl': 0,  # 需要即時報價；請使用 /api/portfolio/performance
        'total_pnl': round(realized_pnl, 2)
    }


def analyze_errors() -> List[Dict]:
    """分析過去失誤操作"""
    trades = get_trades()
    errors = []
    
    for trade in trades:
        # 找出低評分交易
        score = trade.get('score', 5)
        if score and score < 3:
            errors.append(trade)
    
    return errors
