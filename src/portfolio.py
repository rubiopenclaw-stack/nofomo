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
    trade_id = datetime.now().strftime('%Y%m%d_%H%M%S')
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
    """計算損益"""
    trades = get_trades()
    portfolio = get_portfolio()
    
    realized_pnl = 0
    for trade in trades:
        if trade.get('action') == 'SELL' and trade.get('exit_price'):
            pnl = (float(trade.get('exit_price', 0)) - float(trade.get('entry_price', 0))) * float(trade.get('quantity', 0))
            realized_pnl += pnl
    
    # 計算未實現損益
    unrealized_pnl = 0
    
    return {
        'realized_pnl': realized_pnl,
        'unrealized_pnl': unrealized_pnl,
        'total_pnl': realized_pnl + unrealized_pnl
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
