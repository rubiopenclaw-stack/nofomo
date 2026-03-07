"""
股票價格獲取與技術分析
"""

import yfinance as yf
import pandas as pd
from typing import Dict, List, Optional
from datetime import datetime, timedelta


def get_stock_price(ticker: str) -> Dict:
    """取得即時股價"""
    try:
        stock = yf.Ticker(ticker)
        info = stock.info
        
        # 取得近期股價
        hist = stock.history(period='1d')
        current_price = hist['Close'].iloc[-1] if not hist.empty else 0
        
        # 52週高低
        week52 = stock.info.get('fiftyTwoWeekLow', 0), stock.info.get('fiftyTwoWeekHigh', 0)
        
        return {
            'ticker': ticker.upper(),
            'current_price': current_price,
            'currency': info.get('currency', 'USD'),
            'market_cap': info.get('marketCap'),
            'volume': info.get('volume'),
            'week52_low': week52[0],
            'week52_high': week52[1],
            'name': info.get('shortName', ticker),
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {'error': str(e), 'ticker': ticker}


def get_stock_history(ticker: str, period: str = '3mo') -> pd.DataFrame:
    """取得股票歷史數據"""
    try:
        stock = yf.Ticker(ticker)
        return stock.history(period=period)
    except:
        return pd.DataFrame()


def calculate_ma(df: pd.DataFrame, period: int = 20) -> Optional[float]:
    """計算移動平均線"""
    if df.empty or 'Close' not in df:
        return None
    return df['Close'].rolling(window=period).mean().iloc[-1]


def calculate_rsi(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """計算 RSI"""
    if df.empty or 'Close' not in df:
        return None
    
    delta = df['Close'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    return rsi.iloc[-1]


def calculate_macd(df: pd.DataFrame) -> Dict:
    """計算 MACD"""
    if df.empty or 'Close' not in df:
        return {'macd': None, 'signal': None, 'histogram': None}
    
    ema12 = df['Close'].ewm(span=12, adjust=False).mean()
    ema26 = df['Close'].ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    histogram = macd - signal
    
    return {
        'macd': macd.iloc[-1],
        'signal': signal.iloc[-1],
        'histogram': histogram.iloc[-1],
        'crossover': 'GOLDEN' if macd.iloc[-1] > signal.iloc[-1] and macd.iloc[-2] < signal.iloc[-2] else 'DEAD' if macd.iloc[-1] < signal.iloc[-1] and macd.iloc[-2] > signal.iloc[-2] else 'NEUTRAL'
    }


def calculate_bollinger(df: pd.DataFrame, period: int = 20) -> Dict:
    """計算布林通道"""
    if df.empty or 'Close' not in df:
        return {}
    
    sma = df['Close'].rolling(window=period).mean()
    std = df['Close'].rolling(window=period).std()
    
    upper = sma + (std * 2)
    lower = sma - (std * 2)
    
    current_price = df['Close'].iloc[-1]
    
    return {
        'upper': upper.iloc[-1],
        'middle': sma.iloc[-1],
        'lower': lower.iloc[-1],
        'position': 'UPPER' if current_price > upper.iloc[-1] else 'LOWER' if current_price < lower.iloc[-1] else 'MIDDLE'
    }


def technical_analysis(ticker: str) -> Dict:
    """完整技術分析"""
    df = get_stock_history(ticker)
    
    if df.empty:
        return {'error': 'No data available'}
    
    current_price = df['Close'].iloc[-1]
    
    # 各項指標
    ma5 = calculate_ma(df, 5)
    ma20 = calculate_ma(df, 20)
    ma60 = calculate_ma(df, 60) if len(df) >= 60 else None
    rsi = calculate_rsi(df)
    macd = calculate_macd(df)
    bollinger = calculate_bollinger(df)
    
    # 成交量
    volume = df['Volume'].iloc[-1]
    avg_volume = df['Volume'].mean()
    
    # 趨勢判斷
    trend = 'NEUTRAL'
    if ma5 and ma20:
        if ma5 > ma20:
            trend = 'BULLISH'
        elif ma5 < ma20:
            trend = 'BEARISH'
    
    # 評分計算
    score = 0
    
    # 均線多頭排列
    if ma5 and ma20 and ma60 and ma5 > ma20 > ma60:
        score += 2
    elif ma5 and ma20 and ma5 > ma20:
        score += 1
    
    # RSI
    if rsi:
        if rsi < 30:
            score += 2  # 超賣
        elif rsi > 70:
            score -= 1  # 超買
        elif 40 < rsi < 60:
            score += 1  # 合理區間
    
    # MACD
    if macd.get('crossover') == 'GOLDEN':
        score += 2
    elif macd.get('crossover') == 'DEAD':
        score -= 1
    
    # 成交量
    if volume > avg_volume * 1.5:
        score += 1
    
    return {
        'ticker': ticker.upper(),
        'current_price': current_price,
        'ma5': ma5,
        'ma20': ma20,
        'ma60': ma60,
        'rsi': rsi,
        'macd': macd,
        'bollinger': bollinger,
        'volume': volume,
        'avg_volume': avg_volume,
        'trend': trend,
        'score': max(1, min(5, score + 3)),  # 1-5 scale
        'timestamp': datetime.now().isoformat()
    }


def generate_suggestion(analysis: Dict, entry_price: float = None) -> Dict:
    """根據技術分析給出建議"""
    if 'error' in analysis:
        return analysis
    
    score = analysis.get('score', 3)
    rsi = analysis.get('rsi')
    trend = analysis.get('trend')
    current_price = analysis.get('current_price', entry_price)
    
    # 評分對應
    rating = '⭐' * score
    
    # 買入建議
    if score >= 4:
        suggestion = '強烈買入'
    elif score >= 3:
        suggestion = '偏多買入'
    elif score >= 2:
        suggestion = '觀察等待'
    else:
        suggestion = '謹慎操作'
    
    # 停損/目標計算
    if current_price:
        stop_loss = current_price * 0.95  # 5% 止損
        target1 = current_price * 1.10     # 10% 目標
        target2 = current_price * 1.20      # 20% 目標
        risk_reward = 2  # 1:2
        
        suggestion_details = {
            'rating': rating,
            'suggestion': suggestion,
            'stop_loss': round(stop_loss, 2),
            'target_1': round(target1, 2),
            'target_2': round(target2, 2),
            'risk_reward': f'1:{risk_reward}'
        }
    else:
        suggestion_details = {
            'rating': rating,
            'suggestion': suggestion
        }
    
    return suggestion_details
