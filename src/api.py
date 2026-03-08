from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import yfinance as yf
from datetime import datetime, timedelta
import json
from pathlib import Path
import logging
import time
from functools import lru_cache

# Setup logging
LOG_DIR = Path(__file__).parent / 'logs'
LOG_DIR.mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / 'api.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app)

# Paths
BASE_DIR = Path(__file__).parent
UI_DIR = BASE_DIR.parent / 'ui' / 'public'
DATA_DIR = BASE_DIR.parent / 'data'
TRADES_DIR = DATA_DIR / 'trades'
PORTFOLIO_FILE = DATA_DIR / 'portfolio.json'

TRADES_DIR.mkdir(parents=True, exist_ok=True)

# Simple in-memory cache
_price_cache = {}
_cache_ttl_price = 60  # 60 seconds TTL for stock prices
_cache_ttl_analysis = 300  # 5 minutes TTL for technical analysis
_watchlist = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'JPM', 'V', 'WMT']  # Default watchlist


def _get_cached(ticker, cache_type='price'):
    """Get cached data if still valid"""
    key = f"{cache_type}:{ticker.upper()}"
    if key in _price_cache:
        data, timestamp = _price_cache[key]
        # Use different TTL based on cache type
        ttl = _cache_ttl_analysis if cache_type == 'analysis' else _cache_ttl_price
        if time.time() - timestamp < ttl:
            return data
    return None


def _set_cached(ticker, cache_type, data):
    """Set cached data"""
    key = f"{cache_type}:{ticker.upper()}"
    _price_cache[key] = (data, time.time())


def get_stock_price(ticker):
    # Check cache first
    cached = _get_cached(ticker, 'price')
    if cached:
        logger.info(f'Cache hit: {ticker}')
        return cached
    
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='1d')
        if hist.empty:
            return {'error': 'No data'}
        
        current_price = float(hist['Close'].iloc[-1])
        info = stock.info
        
        result = {
            'ticker': ticker.upper(),
            'current_price': current_price,
            'currency': info.get('currency', 'USD'),
            'week52_low': info.get('fiftyTwoWeekLow', 0),
            'week52_high': info.get('fiftyTwoWeekHigh', 0),
            'name': info.get('shortName', ticker),
            'volume': info.get('volume', 0),
            'timestamp': datetime.now().isoformat()
        }
        
        # Cache the result
        _set_cached(ticker, 'price', result)
        return result
    except Exception as e:
        return {'error': str(e)}


def technical_analysis(ticker):
    # Check cache first (5 min TTL for analysis)
    cached = _get_cached(ticker, 'analysis')
    if cached:
        logger.info(f'Analysis cache hit: {ticker}')
        return cached
    
    try:
        stock = yf.Ticker(ticker)
        df = stock.history(period='3mo')
        
        if df.empty:
            return {'error': 'No data'}
        
        current_price = float(df['Close'].iloc[-1])
        
        # MA
        ma5 = float(df['Close'].rolling(5).mean().iloc[-1])
        ma20 = float(df['Close'].rolling(20).mean().iloc[-1])
        ma60 = float(df['Close'].rolling(60).mean().iloc[-1]) if len(df) >= 60 else None
        
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
        
        # Bollinger Bands
        bb_period = 20
        bb_sma = df['Close'].rolling(bb_period).mean()
        bb_std = df['Close'].rolling(bb_period).std()
        bb_upper = bb_sma + (bb_std * 2)
        bb_lower = bb_sma - (bb_std * 2)
        
        # 趨勢
        trend = 'BULLISH' if ma5 > ma20 else 'BEARISH' if ma5 < ma20 else 'NEUTRAL'
        
        # 評分
        score = 3
        if ma5 > ma20 > ma60: score += 2
        elif ma5 > ma20: score += 1
        if rsi < 30: score += 1
        elif rsi > 70: score -= 1
        if macd.iloc[-1] > signal.iloc[-1]: score += 1
        
        score = max(1, min(5, score))
        
        result = {
            'current_price': current_price,
            'ma5': ma5, 'ma20': ma20, 'ma60': ma60,
            'rsi': rsi,
            'macd': float(macd.iloc[-1]),
            'macd_signal': float(signal.iloc[-1]),
            'bollinger': {
                'upper': float(bb_upper.iloc[-1]),
                'middle': float(bb_sma.iloc[-1]),
                'lower': float(bb_lower.iloc[-1]),
                'position': 'UPPER' if current_price > bb_upper.iloc[-1] else 'LOWER' if current_price < bb_lower.iloc[-1] else 'MIDDLE'
            },
            'trend': trend,
            'score': score,
            'rating': '⭐' * score,
            'timestamp': datetime.now().isoformat()
        }
        
        # Cache the result (5 min TTL)
        key = f"analysis:{ticker.upper()}"
        _price_cache[key] = (result, time.time())
        
        return result
    except Exception as e:
        return {'error': str(e)}


# API Routes
@app.route('/api/health')
def health():
    """Health check endpoint"""
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'cache_size': len(_price_cache),
        'cache_ttl': {'price': _cache_ttl, 'analysis': 300},
        'watchlist_count': len(_watchlist)
    })


@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    """Clear the cache"""
    global _price_cache
    _price_cache = {}
    logger.info('Cache cleared')
    return jsonify({'success': True, 'message': 'Cache cleared'})


@app.route('/api/quote')
def quote():
    ticker = request.args.get('ticker', '').upper()
    if not ticker:
        logger.warning('Quote request missing ticker')
        return jsonify({'error': 'Missing ticker'})
    logger.info(f'Quote request: {ticker}')
    result = get_stock_price(ticker)
    if 'error' in result:
        logger.error(f'Quote error for {ticker}: {result["error"]}')
    return jsonify(result)


@app.route('/api/analyze')
def analyze():
    ticker = request.args.get('ticker', '').upper()
    if not ticker:
        logger.warning('Analyze request missing ticker')
        return jsonify({'error': 'Missing ticker'})
    
    logger.info(f'Analyze request: {ticker}')
    analysis = technical_analysis(ticker)
    
    if 'error' not in analysis:
        price = analysis['current_price']
        analysis['stop_loss'] = round(price * 0.95, 2)
        analysis['target_1'] = round(price * 1.10, 2)
        analysis['target_2'] = round(price * 1.20, 2)
        
        scores = {5: '強烈買入', 4: '偏多買入', 3: '觀察等待', 2: '謹慎操作', 1: '不建議'}
        analysis['suggestion'] = scores.get(analysis['score'], '觀察等待')
        logger.info(f'Analyze success: {ticker} score={analysis["score"]}')
    else:
        logger.error(f'Analyze error for {ticker}: {analysis["error"]}')
    
    return jsonify(analysis)


@app.route('/api/trades', methods=['GET'])
def get_trades():
    trades = []
    for f in TRADES_DIR.glob('*.json'):
        with open(f, 'r', encoding='utf-8') as fp:
            trades.append(json.load(fp))
    trades.sort(key=lambda x: x.get('date', ''), reverse=True)
    logger.info(f'Get trades: {len(trades)} records')
    return jsonify(trades)


@app.route('/api/trades', methods=['POST'])
def add_trade():
    data = request.json
    trade_id = datetime.now().strftime('%Y%m%d_%H%M%S')
    data['id'] = trade_id
    data['created_at'] = datetime.now().isoformat()
    
    filepath = TRADES_DIR / f"{trade_id}.json"
    with open(filepath, 'w', encoding='utf-8') as fp:
        json.dump(data, fp, ensure_ascii=False, indent=2)
    
    logger.info(f'New trade added: {data.get("ticker")} {data.get("action")} {data.get("quantity")}')
    return jsonify({'success': True, 'id': trade_id})


@app.route('/api/portfolio')
def get_portfolio():
    if PORTFOLIO_FILE.exists():
        with open(PORTFOLIO_FILE, 'r', encoding='utf-8') as fp:
            return jsonify(json.load(fp))
    return jsonify({'positions': [], 'cash': 0})


@app.route('/api/batch-quote')
def batch_quote():
    """Batch quote for multiple tickers"""
    tickers = request.args.get('tickers', '').upper().split(',')
    tickers = [t.strip() for t in tickers if t.strip()]
    
    if not tickers:
        return jsonify({'error': 'Missing tickers'})
    
    if len(tickers) > 20:
        return jsonify({'error': 'Max 20 tickers allowed'})
    
    results = {}
    for ticker in tickers:
        results[ticker] = get_stock_price(ticker)
    
    logger.info(f'Batch quote: {len(tickers)} tickers')
    return jsonify(results)


@app.route('/api/watchlist')
def get_watchlist():
    """Get watchlist"""
    return jsonify({'watchlist': _watchlist})


@app.route('/api/watchlist', methods=['POST'])
def update_watchlist():
    """Update watchlist"""
    global _watchlist
    data = request.json
    if 'watchlist' in data:
        _watchlist = [t.upper().strip() for t in data['watchlist'] if t.strip()]
        logger.info(f'Watchlist updated: {_watchlist}')
        return jsonify({'success': True, 'watchlist': _watchlist})
    return jsonify({'error': 'Invalid request'})


@app.route('/api/history')
def get_history():
    """Get historical price data"""
    ticker = request.args.get('ticker', '').upper()
    period = request.args.get('period', '1mo')  # 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max
    
    if not ticker:
        return jsonify({'error': 'Missing ticker'})
    
    valid_periods = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max']
    if period not in valid_periods:
        return jsonify({'error': f'Invalid period. Valid: {valid_periods}'})
    
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        
        if hist.empty:
            return jsonify({'error': 'No data'})
        
        # Convert to list of dicts
        data = []
        for idx, row in hist.iterrows():
            data.append({
                'date': idx.isoformat(),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row['Volume'])
            })
        
        logger.info(f'History: {ticker} {period} {len(data)} days')
        return jsonify({
            'ticker': ticker,
            'period': period,
            'data': data,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f'History error: {ticker} {e}')
        return jsonify({'error': str(e)})


@app.route('/api/portfolio/performance')
def portfolio_performance():
    """Calculate portfolio performance"""
    # Get trades
    trades = []
    for f in TRADES_DIR.glob('*.json'):
        with open(f, 'r', encoding='utf-8') as fp:
            trades.append(json.load(fp))
    
    if not trades:
        return jsonify({'total_value': 0, 'total_cost': 0, 'pnl': 0, 'pnl_percent': 0})
    
    # Aggregate positions
    positions = {}
    total_cost = 0
    
    for trade in trades:
        ticker = trade.get('ticker', '').upper()
        action = trade.get('action', '').lower()
        quantity = int(trade.get('quantity', 0))
        price = float(trade.get('price', 0))
        
        if ticker not in positions:
            positions[ticker] = {'quantity': 0, 'avg_price': 0, 'cost': 0}
        
        if action == 'buy':
            old_qty = positions[ticker]['quantity']
            old_cost = positions[ticker]['cost']
            new_cost = old_cost + (quantity * price)
            new_qty = old_qty + quantity
            positions[ticker]['quantity'] = new_qty
            positions[ticker]['avg_price'] = new_cost / new_qty if new_qty > 0 else 0
            positions[ticker]['cost'] = new_cost
            total_cost += quantity * price
        elif action == 'sell':
            positions[ticker]['quantity'] -= quantity
            positions[ticker]['cost'] -= quantity * positions[ticker]['avg_price']
            total_cost -= quantity * price
    
    # Get current prices and calculate P&L
    total_value = 0
    position_details = []
    
    for ticker, pos in positions.items():
        if pos['quantity'] > 0:
            current_price = get_stock_price(ticker)
            if 'error' not in current_price:
                current_value = pos['quantity'] * current_price['current_price']
                cost_basis = pos['quantity'] * pos['avg_price']
                pnl = current_value - cost_basis
                pnl_percent = (pnl / cost_basis * 100) if cost_basis > 0 else 0
                
                position_details.append({
                    'ticker': ticker,
                    'quantity': pos['quantity'],
                    'avg_price': round(pos['avg_price'], 2),
                    'current_price': current_price['current_price'],
                    'value': round(current_value, 2),
                    'cost': round(cost_basis, 2),
                    'pnl': round(pnl, 2),
                    'pnl_percent': round(pnl_percent, 2)
                })
                total_value += current_value
    
    total_pnl = total_value - total_cost
    total_pnl_percent = (total_pnl / total_cost * 100) if total_cost > 0 else 0
    
    logger.info(f'Portfolio perf: value={total_value} cost={total_cost} pnl={total_pnl}')
    
    return jsonify({
        'positions': position_details,
        'total_value': round(total_value, 2),
        'total_cost': round(total_cost, 2),
        'pnl': round(total_pnl, 2),
        'pnl_percent': round(total_pnl_percent, 2),
        'timestamp': datetime.now().isoformat()
    })


# Price alert storage (in-memory)
_price_alerts = {}


@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    """Get all price alerts"""
    return jsonify({'alerts': _price_alerts})


@app.route('/api/alerts', methods=['POST'])
def set_alert():
    """Set a price alert"""
    data = request.json
    ticker = data.get('ticker', '').upper()
    target_price = float(data.get('target_price', 0))
    condition = data.get('condition', 'above')  # above, below
    
    if not ticker or target_price <= 0:
        return jsonify({'error': 'Invalid ticker or price'})
    
    if ticker not in _price_alerts:
        _price_alerts[ticker] = []
    
    alert = {
        'target_price': target_price,
        'condition': condition,
        'created_at': datetime.now().isoformat(),
        'triggered': False
    }
    _price_alerts[ticker].append(alert)
    
    logger.info(f'Alert set: {ticker} {condition} {target_price}')
    return jsonify({'success': True, 'alert': alert})


@app.route('/api/alerts', methods=['DELETE'])
def clear_alerts():
    """Clear all alerts"""
    global _price_alerts
    _price_alerts = {}
    logger.info('All alerts cleared')
    return jsonify({'success': True})


@app.route('/api/alerts/check')
def check_alerts():
    """Check if any alerts are triggered"""
    triggered = []
    
    for ticker, alerts in _price_alerts.items():
        current = get_stock_price(ticker)
        if 'error' in current:
            continue
        
        price = current['current_price']
        for alert in alerts:
            if alert['triggered']:
                continue
            
            is_triggered = False
            if alert['condition'] == 'above' and price >= alert['target_price']:
                is_triggered = True
            elif alert['condition'] == 'below' and price <= alert['target_price']:
                is_triggered = True
            
            if is_triggered:
                alert['triggered'] = True
                alert['triggered_at'] = datetime.now().isoformat()
                alert['current_price'] = price
                triggered.append({
                    'ticker': ticker,
                    'target_price': alert['target_price'],
                    'condition': alert['condition'],
                    'current_price': price
                })
    
    logger.info(f'Alerts checked: {len(triggered)} triggered')
    return jsonify({
        'triggered': triggered,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/risk评估')
def risk_assessment():
    """Calculate portfolio risk metrics"""
    # Get portfolio performance data
    perf_response = portfolio_performance()
    perf_data = perf_response.get_json()
    
    if not perf_data.get('positions'):
        return jsonify({'risk_level': 'N/A', 'message': 'No positions'})
    
    # Calculate risk metrics
    positions = perf_data['positions']
    total_value = perf_data['total_value']
    
    # Position concentration
    max_position = max([p['value'] / total_value for p in positions]) if total_value > 0 else 0
    concentration_risk = 'HIGH' if max_position > 0.4 else 'MEDIUM' if max_position > 0.25 else 'LOW'
    
    # P&L distribution
    profitable = sum(1 for p in positions if p['pnl'] > 0)
    losing = sum(1 for p in positions if p['pnl'] < 0)
    win_rate = profitable / len(positions) * 100 if positions else 0
    
    # Overall risk score (1-10, higher = riskier)
    risk_score = 5
    if concentration_risk == 'HIGH': risk_score += 2
    elif concentration_risk == 'MEDIUM': risk_score += 1
    if win_rate < 40: risk_score += 2
    elif win_rate < 60: risk_score += 1
    
    risk_level = 'HIGH' if risk_score >= 7 else 'MEDIUM' if risk_score >= 4 else 'LOW'
    
    recommendations = []
    if concentration_risk == 'HIGH':
        recommendations.append('建議分散投資，降低單一標的比重')
    if win_rate < 50:
        recommendations.append('建議檢視虧損部位，考慮停損')
    if len(positions) < 3:
        recommendations.append('建議增加投資標的數量分散風險')
    
    logger.info(f'Risk assessment: level={risk_level} score={risk_score}')
    
    return jsonify({
        'risk_level': risk_level,
        'risk_score': risk_score,
        'concentration': concentration_risk,
        'win_rate': round(win_rate, 1),
        'positions_count': len(positions),
        'recommendations': recommendations,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/signals')
def trading_signals():
    """Generate trading signals for watchlist"""
    signals = []
    
    for ticker in _watchlist[:5]:  # Limit to 5 for performance
        try:
            analysis = technical_analysis(ticker)
            if 'error' not in analysis:
                signal = {
                    'ticker': ticker,
                    'price': analysis['current_price'],
                    'trend': analysis['trend'],
                    'rsi': round(analysis['rsi'], 1),
                    'score': analysis['score'],
                    'suggestion': analysis['suggestion']
                }
                
                # 交易訊號
                if analysis['rsi'] < 30 and analysis['trend'] == 'BULLISH':
                    signal['action'] = '🔥 強烈買入'
                elif analysis['rsi'] < 40:
                    signal['action'] = '📈 考慮買入'
                elif analysis['rsi'] > 70:
                    signal['action'] = '⚠️ 考慮賣出'
                else:
                    signal['action'] = '➡️ 觀望'
                
                signals.append(signal)
        except Exception as e:
            logger.error(f'Signal error: {ticker} {e}')
    
    logger.info(f'Signals generated: {len(signals)}')
    return jsonify({
        'signals': signals,
        'timestamp': datetime.now().isoformat()
    })


@app.route('/api/trades/analysis')
def trades_analysis():
    """Analyze trading history"""
    trades = []
    for f in TRADES_DIR.glob('*.json'):
        with open(f, 'r', encoding='utf-8') as fp:
            trades.append(json.load(fp))
    
    if not trades:
        return jsonify({'message': 'No trades'})
    
    # Statistics
    total_trades = len(trades)
    buy_trades = [t for t in trades if t.get('action', '').lower() == 'buy']
    sell_trades = [t for t in trades if t.get('action', '').lower() == 'sell']
    
    # By ticker
    ticker_stats = {}
    for trade in trades:
        ticker = trade.get('ticker', '').upper()
        if ticker not in ticker_stats:
            ticker_stats[ticker] = {'buy': 0, 'sell': 0, 'total': 0}
        ticker_stats[ticker][trade.get('action', '').lower()] += 1
        ticker_stats[ticker]['total'] += 1
    
    # Recent activity
    recent = sorted(trades, key=lambda x: x.get('created_at', ''), reverse=True)[:5]
    
    logger.info(f'Trades analysis: {total_trades} trades')
    
    return jsonify({
        'total_trades': total_trades,
        'buy_count': len(buy_trades),
        'sell_count': len(sell_trades),
        'by_ticker': ticker_stats,
        'recent_trades': recent,
        'timestamp': datetime.now().isoformat()
    })


# Serve UI
@app.route('/')
def index():
    index_path = UI_DIR / 'index.html'
    if index_path.exists():
        return index_path.read_text(encoding='utf-8')
    return '<h1>NoFOMO</h1><p>UI not found</p>'

@app.route('/jobs')
def jobs():
    jobs_path = UI_DIR / '..' / 'ui' / 'jobs.html'
    if jobs_path.exists():
        return jobs_path.read_text(encoding='utf-8')
    # Try alternate path
    jobs_path2 = Path(__file__).parent.parent / 'ui' / 'jobs.html'
    if jobs_path2.exists():
        return jobs_path2.read_text(encoding='utf-8')
    return '<h1>Jobs</h1><p>Not found</p>'


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
