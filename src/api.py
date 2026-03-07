from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS
import yfinance as yf
from datetime import datetime
import json
from pathlib import Path
import logging

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


def get_stock_price(ticker):
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period='1d')
        if hist.empty:
            return {'error': 'No data'}
        
        current_price = float(hist['Close'].iloc[-1])
        info = stock.info
        
        return {
            'ticker': ticker.upper(),
            'current_price': current_price,
            'currency': info.get('currency', 'USD'),
            'week52_low': info.get('fiftyTwoWeekLow', 0),
            'week52_high': info.get('fiftyTwoWeekHigh', 0),
            'name': info.get('shortName', ticker),
            'volume': info.get('volume', 0),
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {'error': str(e)}


def technical_analysis(ticker):
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
        
        return {
            'current_price': current_price,
            'ma5': ma5, 'ma20': ma20, 'ma60': ma60,
            'rsi': rsi,
            'macd': float(macd.iloc[-1]),
            'macd_signal': float(signal.iloc[-1]),
            'trend': trend,
            'score': score,
            'rating': '⭐' * score,
            'timestamp': datetime.now().isoformat()
        }
    except Exception as e:
        return {'error': str(e)}


# API Routes
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
