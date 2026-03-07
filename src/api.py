"""
NoFOMO Backend API - Flask + yfinance
"""

from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
import pandas as pd
from datetime import datetime
import json
from pathlib import Path

app = Flask(__name__)
CORS(app)

# Data directory
DATA_DIR = Path(__file__).parent.parent / 'data'
TRADES_DIR = DATA_DIR / 'trades'
PORTFOLIO_FILE = DATA_DIR / 'portfolio.json'

TRADES_DIR.mkdir(parents=True, exist_ok=True)


def get_stock_price(ticker: str):
    """取得即時股價"""
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='1d')
        
        if hist.empty:
            return {'error': 'No data'}
        
        current_price = float(hist['Close'].iloc[-1])
        info = stock.info
        
        # 52週高低
        week52_low = info.get('fiftyTwoWeekLow', 0)
        week52_high = info.get('fiftyTwoWeekHigh', 0)
        
        return {
            'ticker': ticker.upper(),
            'current_price': current_price,
            'currency': info.get('currency', 'USD'),
            'week52_low': week52_low,
            'week52_high': week52_high,
            'name': info.get('shortName', ticker),
            'volume': info.get('volume', 0),
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {'error': str(e)}


def technical_analysis(ticker: str):
    """技術分析"""
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period='3mo')
        
        if df.empty:
            return {'error': 'No data'}
        
        current_price = float(df['Close'].iloc[-1])
        
        # MA
        ma20 = float(df['Close'].rolling(20).mean().iloc[-1])
        ma60 = float(df['Close'].rolling(60).mean().iloc[-1]) if len(df) >= 60 else None
        ma5 = float(df['Close'].rolling(5).mean().iloc[-1])
        
        # RSI
        delta = df['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
        rs = gain / loss
        rsi = float(100 - (100 / (1 + rs)).iloc[-1])
        
        # MACD
        ema12 = df['Close'].ewm(span=12).mean()
        ema26 = df['Close'].ewm(span=26).mean()
        macd = ema12 - ema26
        signal = macd.ewm(span=9).mean()
        macd_hist = macd - signal
        
        # 趨勢
        if ma5 > ma20:
            trend = 'BULLISH'
        elif ma5 < ma20:
            trend = 'BEARISH'
        else:
            trend = 'NEUTRAL'
        
        # 評分
        score = 3
        if ma5 > ma20 > ma60:
            score += 2
        elif ma5 > ma20:
            score += 1
        
        if rsi < 30:
            score += 1
        elif rsi > 70:
            score -= 1
        
        if macd.iloc[-1] > signal.iloc[-1]:
            score += 1
        
        score = max(1, min(5, score))
        
        # 成交量
        volume = int(df['Volume'].iloc[-1])
        avg_volume = int(df['Volume'].mean())
        if volume > avg_volume * 1.5:
            score += 1
        
        return {
            'current_price': current_price,
            'ma5': ma5,
            'ma20': ma20,
            'ma60': ma60,
            'rsi': rsi,
            'macd': float(macd.iloc[-1]),
            'macd_signal': float(signal.iloc[-1]),
            'macd_hist': float(macd_hist.iloc[-1]),
            'volume': volume,
            'avg_volume': avg_volume,
            'trend': trend,
            'score': score,
            'rating': '⭐' * score,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {'error': str(e)}


@app.route('/api/quote', methods=['GET'])
def quote():
    """查詢股價"""
    ticker = request.args.get('ticker', '').upper()
    if not ticker:
        return jsonify({'error': 'Missing ticker'})
    
    price = get_stock_price(ticker)
    return jsonify(price)


@app.route('/api/analyze', methods=['GET'])
def analyze():
    """技術分析"""
    ticker = request.args.get('ticker', '').upper()
    if not ticker:
        return jsonify({'error': 'Missing ticker'})
    
    analysis = technical_analysis(ticker)
    
    # 計算建議
    if 'error' not in analysis:
        price = analysis['current_price']
        score = analysis['score']
        
        analysis['stop_loss'] = round(price * 0.95, 2)
        analysis['target_1'] = round(price * 1.10, 2)
        analysis['target_2'] = round(price * 1.20, 2)
        
        if score >= 4:
            analysis['suggestion'] = '強烈買入'
        elif score >= 3:
            analysis['suggestion'] = '偏多買入'
        elif score >= 2:
            analysis['suggestion'] = '觀察等待'
        else:
            analysis['suggestion'] = '謹慎操作'
    
    return jsonify(analysis)


@app.route('/api/trades', methods=['GET'])
def get_trades():
    """取得所有交易"""
    trades = []
    for f in TRADES_DIR.glob('*.json'):
        with open(f, 'r', encoding='utf-8') as fp:
            trades.append(json.load(fp))
    trades.sort(key=lambda x: x.get('date', ''), reverse=True)
    return jsonify(trades)


@app.route('/api/trades', methods=['POST'])
def add_trade():
    """新增交易"""
    data = request.json
    
    trade_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    data['id'] = trade_id
    data['created_at'] = datetime.now().isoformat()
    
    filepath = TRADES_DIR / f"{trade_id}.json"
    with open(filepath, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    
    return jsonify({'success': True, 'id': trade_id})


@app.route('/api/portfolio', methods=['GET'])
def get_portfolio():
    """取得持倉"""
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as fp:
            return jsonify(json.load(fp))
    return jsonify({'positions': [], 'cash': 0})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
