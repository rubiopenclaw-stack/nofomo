import sys
from pathlib import Path

# 確保 src/ 在 import 路徑中（支援直接執行或作為模組）
sys.path.insert(0, str(Path(__file__).parent))

from flask import Flask, jsonify, request
from flask_cors import CORS
import yfinance as yf
from datetime import datetime
import json
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor

from analyzer import (
    get_stock_price as _fetch_price,
    technical_analysis as _compute_analysis,
    get_stock_history as _get_stock_history,
)

# ---------------------------------------------------------------------------
# 線程安全的 JSON 檔案操作
# ---------------------------------------------------------------------------
_file_locks: dict = {}
_file_locks_lock = threading.Lock()


def get_file_lock(filepath):
    """取得或建立對應檔案的鎖（thread-safe）"""
    filepath = str(filepath)
    with _file_locks_lock:
        if filepath not in _file_locks:
            _file_locks[filepath] = threading.Lock()
        return _file_locks[filepath]


def safe_json_write(filepath, data):
    """Thread-safe JSON 寫入"""
    lock = get_file_lock(filepath)
    with lock:
        with open(filepath, 'w', encoding='utf-8') as fp:
            json.dump(data, fp, ensure_ascii=False, indent=2)


def safe_json_read(filepath):
    """Thread-safe JSON 讀取"""
    lock = get_file_lock(filepath)
    with lock:
        with open(filepath, 'r', encoding='utf-8') as fp:
            return json.load(fp)


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
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

# ---------------------------------------------------------------------------
# Flask app
# ---------------------------------------------------------------------------
app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------------------------
# 路徑
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).parent
UI_DIR = BASE_DIR.parent / 'ui' / 'public'
DATA_DIR = BASE_DIR.parent / 'data'
TRADES_DIR = DATA_DIR / 'trades'
PORTFOLIO_FILE = DATA_DIR / 'portfolio.json'
WATCHLIST_FILE = DATA_DIR / 'watchlist.json'
ALERTS_FILE = DATA_DIR / 'alerts.json'

TRADES_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# 內存快取（附鎖）
# ---------------------------------------------------------------------------
_price_cache: dict = {}
_cache_lock = threading.Lock()
_cache_ttl_price = 60      # 60 秒
_cache_ttl_analysis = 300  # 5 分鐘


def _get_cached(ticker, cache_type='price'):
    key = f"{cache_type}:{ticker.upper()}"
    with _cache_lock:
        if key in _price_cache:
            data, timestamp = _price_cache[key]
            ttl = _cache_ttl_analysis if cache_type == 'analysis' else _cache_ttl_price
            if time.time() - timestamp < ttl:
                return data
    return None


def _set_cached(ticker, cache_type, data):
    key = f"{cache_type}:{ticker.upper()}"
    with _cache_lock:
        _price_cache[key] = (data, time.time())


# ---------------------------------------------------------------------------
# 關注清單 & 提醒（持久化到 data/）
# ---------------------------------------------------------------------------
_DEFAULT_WATCHLIST = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'NVDA', 'TSLA', 'META', 'JPM', 'V', 'WMT']


def _load_watchlist():
    if WATCHLIST_FILE.exists():
        return safe_json_read(WATCHLIST_FILE)
    return list(_DEFAULT_WATCHLIST)


def _save_watchlist(watchlist):
    safe_json_write(WATCHLIST_FILE, watchlist)


def _load_alerts():
    if ALERTS_FILE.exists():
        return safe_json_read(ALERTS_FILE)
    return {}


def _save_alerts(alerts):
    safe_json_write(ALERTS_FILE, alerts)


_watchlist = _load_watchlist()
_price_alerts = _load_alerts()

# ---------------------------------------------------------------------------
# 業務邏輯：股價 & 分析（帶快取，委託 analyzer.py 計算）
# ---------------------------------------------------------------------------
_SUGGESTION_MAP = {5: '強烈買入', 4: '偏多買入', 3: '觀察等待', 2: '謹慎操作', 1: '不建議'}


def get_stock_price(ticker):
    """取得即時股價（帶快取）"""
    cached = _get_cached(ticker, 'price')
    if cached:
        logger.info(f'Cache hit: {ticker}')
        return cached
    result = _fetch_price(ticker)
    if 'error' not in result:
        _set_cached(ticker, 'price', result)
    return result


def technical_analysis(ticker):
    """技術分析（帶快取，並展平 MACD dict 以維持 API 相容性）"""
    cached = _get_cached(ticker, 'analysis')
    if cached:
        logger.info(f'Analysis cache hit: {ticker}')
        return cached

    result = _compute_analysis(ticker)
    if 'error' not in result:
        # 將 analyzer.py 回傳的 macd dict 展平，保持原有 API 格式
        macd_data = result.get('macd', {})
        if isinstance(macd_data, dict):
            result['macd'] = macd_data.get('macd')
            result['macd_signal'] = macd_data.get('signal')
            result['macd_histogram'] = macd_data.get('histogram')
            result['macd_crossover'] = macd_data.get('crossover')
        _set_cached(ticker, 'analysis', result)

    return result


# ---------------------------------------------------------------------------
# 共用輔助：交易 & 投資組合
# ---------------------------------------------------------------------------

def _load_all_trades():
    """Thread-safe 讀取所有交易檔案"""
    trades = []
    for f in TRADES_DIR.glob('*.json'):
        try:
            trades.append(safe_json_read(f))
        except Exception as e:
            logger.error(f'Failed to read trade file {f}: {e}')
    return trades


def _aggregate_positions(trades):
    """將交易清單聚合成目前持倉（含平均成本）"""
    positions: dict = {}
    for trade in trades:
        ticker = trade.get('ticker', '').upper()
        action = trade.get('action', '').lower()
        quantity = int(trade.get('quantity', 0))
        price = float(trade.get('entry_price', 0) or trade.get('price', 0))

        if not ticker:
            continue

        if ticker not in positions:
            positions[ticker] = {'quantity': 0, 'cost': 0.0, 'avg_price': 0.0}

        if action == 'buy':
            old_qty = positions[ticker]['quantity']
            old_cost = positions[ticker]['cost']
            new_cost = old_cost + quantity * price
            new_qty = old_qty + quantity
            positions[ticker]['quantity'] = new_qty
            positions[ticker]['cost'] = new_cost
            positions[ticker]['avg_price'] = new_cost / new_qty if new_qty > 0 else 0.0

        elif action == 'sell':
            avg = positions[ticker]['avg_price']
            positions[ticker]['quantity'] -= quantity
            positions[ticker]['cost'] -= quantity * avg

    return {t: p for t, p in positions.items() if p['quantity'] > 0}


def _enrich_positions_with_prices(positions):
    """並行查詢現價，計算每個部位的損益，回傳 (details_list, total_value)"""
    def fetch_one(ticker, pos):
        price_data = get_stock_price(ticker)
        if 'error' in price_data:
            return None
        current_price = price_data['current_price']
        current_value = pos['quantity'] * current_price
        pnl = current_value - pos['cost']
        pnl_pct = (pnl / pos['cost'] * 100) if pos['cost'] > 0 else 0.0
        return {
            'ticker': ticker,
            'quantity': pos['quantity'],
            'avg_price': round(pos['avg_price'], 2),
            'current_price': round(current_price, 2),
            'value': round(current_value, 2),
            'cost': round(pos['cost'], 2),
            'pnl': round(pnl, 2),
            'pnl_pct': round(pnl_pct, 2),
        }

    details = []
    total_value = 0.0

    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {
            ticker: executor.submit(fetch_one, ticker, pos)
            for ticker, pos in positions.items()
        }
        for ticker, future in futures.items():
            result = future.result()
            if result:
                details.append(result)
                total_value += result['value']

    return details, total_value


# ---------------------------------------------------------------------------
# API Routes
# ---------------------------------------------------------------------------

@app.route('/api/health')
def health():
    with _cache_lock:
        cache_size = len(_price_cache)
    return jsonify({
        'status': 'ok',
        'timestamp': datetime.now().isoformat(),
        'cache_size': cache_size,
        'cache_ttl': {'price': _cache_ttl_price, 'analysis': _cache_ttl_analysis},
        'watchlist_count': len(_watchlist)
    })


@app.route('/api/cache/clear', methods=['POST'])
def clear_cache():
    with _cache_lock:
        _price_cache.clear()
    logger.info('Cache cleared')
    return jsonify({'success': True, 'message': 'Cache cleared'})


@app.route('/api/quote')
def quote():
    ticker = request.args.get('ticker', '').upper()
    if not ticker:
        return jsonify({'error': 'Missing ticker'}), 400
    logger.info(f'Quote request: {ticker}')
    result = get_stock_price(ticker)
    if 'error' in result:
        logger.error(f'Quote error for {ticker}: {result["error"]}')
        return jsonify(result), 502
    return jsonify(result)


@app.route('/api/analyze')
def analyze():
    ticker = request.args.get('ticker', '').upper()
    if not ticker:
        return jsonify({'error': 'Missing ticker'}), 400

    logger.info(f'Analyze request: {ticker}')
    analysis = technical_analysis(ticker)

    if 'error' in analysis:
        logger.error(f'Analyze error for {ticker}: {analysis["error"]}')
        return jsonify(analysis), 502

    price = analysis['current_price']
    analysis['stop_loss'] = round(price * 0.95, 2)
    analysis['target_1'] = round(price * 1.10, 2)
    analysis['target_2'] = round(price * 1.20, 2)
    analysis['suggestion'] = _SUGGESTION_MAP.get(analysis['score'], '觀察等待')
    analysis['rating'] = '⭐' * analysis['score']
    logger.info(f'Analyze success: {ticker} score={analysis["score"]}')
    return jsonify(analysis)


@app.route('/api/trades', methods=['GET'])
def get_trades():
    trades = _load_all_trades()
    trades.sort(key=lambda x: x.get('date', ''), reverse=True)
    logger.info(f'Get trades: {len(trades)} records')
    return jsonify(trades)


@app.route('/api/trades', methods=['POST'])
def add_trade():
    data = request.json
    if not data:
        return jsonify({'error': 'Missing request body'}), 400

    # 必填欄位驗證
    required = ['ticker', 'action', 'quantity', 'entry_price']
    missing = [f for f in required if not data.get(f)]
    if missing:
        return jsonify({'error': f'Missing fields: {missing}'}), 400

    # 含微秒避免同秒衝突
    trade_id = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    data['id'] = trade_id
    data['created_at'] = datetime.now().isoformat()

    filepath = TRADES_DIR / f"{trade_id}.json"
    safe_json_write(filepath, data)

    logger.info(f'New trade added: {data.get("ticker")} {data.get("action")} {data.get("quantity")}')
    return jsonify({'success': True, 'id': trade_id})


@app.route('/api/portfolio')
def get_portfolio():
    if PORTFOLIO_FILE.exists():
        return jsonify(safe_json_read(PORTFOLIO_FILE))
    return jsonify({'positions': [], 'cash': 0})


@app.route('/api/portfolio/summary')
def portfolio_summary():
    trades = _load_all_trades()
    if not trades:
        return jsonify({
            'cash': 5000, 'stock_value': 0, 'total_assets': 5000,
            'total_cost': 0, 'total_pnl': 0, 'total_pnl_pct': 0, 'positions': []
        })

    positions = _aggregate_positions(trades)
    total_cost = sum(p['cost'] for p in positions.values())
    position_details, stock_value = _enrich_positions_with_prices(positions)

    cash = 5000
    total_assets = cash + stock_value
    total_pnl = stock_value - total_cost
    total_pnl_pct = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    return jsonify({
        'cash': cash,
        'stock_value': round(stock_value, 2),
        'total_assets': round(total_assets, 2),
        'total_cost': round(total_cost, 2),
        'total_pnl': round(total_pnl, 2),
        'total_pnl_pct': round(total_pnl_pct, 2),
        'positions': position_details,
        'updated_at': datetime.now().isoformat()
    })


@app.route('/api/batch-quote')
def batch_quote():
    tickers = request.args.get('tickers', '').upper().split(',')
    tickers = [t.strip() for t in tickers if t.strip()]

    if not tickers:
        return jsonify({'error': 'Missing tickers'}), 400
    if len(tickers) > 20:
        return jsonify({'error': 'Max 20 tickers allowed'}), 400

    # 並行查詢
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = {ticker: executor.submit(get_stock_price, ticker) for ticker in tickers}
        results = {ticker: future.result() for ticker, future in futures.items()}

    logger.info(f'Batch quote: {len(tickers)} tickers')
    return jsonify(results)


@app.route('/api/watchlist')
def get_watchlist():
    return jsonify({'watchlist': _watchlist})


@app.route('/api/watchlist', methods=['POST'])
def update_watchlist():
    global _watchlist
    data = request.json
    if not data or 'watchlist' not in data:
        return jsonify({'error': 'Invalid request'}), 400
    _watchlist = [t.upper().strip() for t in data['watchlist'] if t.strip()]
    _save_watchlist(_watchlist)
    logger.info(f'Watchlist updated: {_watchlist}')
    return jsonify({'success': True, 'watchlist': _watchlist})


@app.route('/api/history')
def get_history():
    ticker = request.args.get('ticker', '').upper()
    period = request.args.get('period', '1mo')

    if not ticker:
        return jsonify({'error': 'Missing ticker'}), 400

    valid_periods = ['1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max']
    if period not in valid_periods:
        return jsonify({'error': f'Invalid period. Valid: {valid_periods}'}), 400

    try:
        hist = _get_stock_history(ticker, period)
        if hist.empty:
            return jsonify({'error': 'No data'}), 404

        data = [
            {
                'date': idx.isoformat(),
                'open': float(row['Open']),
                'high': float(row['High']),
                'low': float(row['Low']),
                'close': float(row['Close']),
                'volume': int(row['Volume'])
            }
            for idx, row in hist.iterrows()
        ]

        logger.info(f'History: {ticker} {period} {len(data)} days')
        return jsonify({
            'ticker': ticker,
            'period': period,
            'data': data,
            'timestamp': datetime.now().isoformat()
        })
    except Exception as e:
        logger.error(f'History error: {ticker} {e}')
        return jsonify({'error': str(e)}), 500


@app.route('/api/portfolio/performance')
def portfolio_performance():
    trades = _load_all_trades()
    if not trades:
        return jsonify({'total_value': 0, 'total_cost': 0, 'pnl': 0, 'pnl_percent': 0})

    positions = _aggregate_positions(trades)
    total_cost = sum(p['cost'] for p in positions.values())
    position_details, total_value = _enrich_positions_with_prices(positions)

    # 此端點歷史欄位名為 pnl_percent
    for p in position_details:
        p['pnl_percent'] = p.pop('pnl_pct')

    total_pnl = total_value - total_cost
    total_pnl_percent = (total_pnl / total_cost * 100) if total_cost > 0 else 0

    logger.info(f'Portfolio perf: value={total_value:.2f} cost={total_cost:.2f} pnl={total_pnl:.2f}')
    return jsonify({
        'positions': position_details,
        'total_value': round(total_value, 2),
        'total_cost': round(total_cost, 2),
        'pnl': round(total_pnl, 2),
        'pnl_percent': round(total_pnl_percent, 2),
        'timestamp': datetime.now().isoformat()
    })


# ---------------------------------------------------------------------------
# 價格提醒
# ---------------------------------------------------------------------------

@app.route('/api/alerts', methods=['GET'])
def get_alerts():
    return jsonify({'alerts': _price_alerts})


@app.route('/api/alerts', methods=['POST'])
def set_alert():
    data = request.json
    if not data:
        return jsonify({'error': 'Missing request body'}), 400

    ticker = data.get('ticker', '').upper()
    
    # 輸入驗證
    try:
        target_price = float(data.get('target_price', 0))
    except (TypeError, ValueError):
        return jsonify({'error': 'Invalid target_price'}), 400
    
    condition = data.get('condition', 'above')

    if not ticker or target_price <= 0:
        return jsonify({'error': 'Invalid ticker or price'}), 400

    if ticker not in _price_alerts:
        _price_alerts[ticker] = []

    alert = {
        'target_price': target_price,
        'condition': condition,
        'created_at': datetime.now().isoformat(),
        'triggered': False
    }
    _price_alerts[ticker].append(alert)
    _save_alerts(_price_alerts)

    logger.info(f'Alert set: {ticker} {condition} {target_price}')
    return jsonify({'success': True, 'alert': alert})


@app.route('/api/alerts', methods=['DELETE'])
def clear_alerts():
    global _price_alerts
    _price_alerts = {}
    _save_alerts(_price_alerts)
    logger.info('All alerts cleared')
    return jsonify({'success': True})


@app.route('/api/alerts/check')
def check_alerts():
    triggered = []
    any_changed = False

    for ticker, alerts in _price_alerts.items():
        current = get_stock_price(ticker)
        if 'error' in current:
            continue

        price = current['current_price']
        for alert in alerts:
            if alert['triggered']:
                continue

            is_triggered = (
                (alert['condition'] == 'above' and price >= alert['target_price']) or
                (alert['condition'] == 'below' and price <= alert['target_price'])
            )
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
                any_changed = True

    # 統一儲存（避免每個 ticker 都寫一次）
    if any_changed:
        _save_alerts(_price_alerts)

    logger.info(f'Alerts checked: {len(triggered)} triggered')
    return jsonify({'triggered': triggered, 'timestamp': datetime.now().isoformat()})


# ---------------------------------------------------------------------------
# 風險評估
# ---------------------------------------------------------------------------

@app.route('/api/risk-assessment')
def risk_assessment():
    perf_response = portfolio_performance()
    perf_data = perf_response.get_json()

    if not perf_data.get('positions'):
        return jsonify({'risk_level': 'N/A', 'message': 'No positions'})

    positions = perf_data['positions']
    total_value = perf_data['total_value']

    max_position = max(p['value'] / total_value for p in positions) if total_value > 0 else 0
    concentration_risk = 'HIGH' if max_position > 0.4 else 'MEDIUM' if max_position > 0.25 else 'LOW'

    profitable = sum(1 for p in positions if p['pnl'] > 0)
    win_rate = profitable / len(positions) * 100 if positions else 0

    risk_score = 5
    if concentration_risk == 'HIGH':
        risk_score += 2
    elif concentration_risk == 'MEDIUM':
        risk_score += 1
    if win_rate < 40:
        risk_score += 2
    elif win_rate < 60:
        risk_score += 1

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


# ---------------------------------------------------------------------------
# 交易訊號
# ---------------------------------------------------------------------------

@app.route('/api/signals')
def trading_signals():
    signals = []

    for ticker in _watchlist[:5]:
        try:
            analysis = technical_analysis(ticker)
            if 'error' in analysis:
                continue

            rsi = analysis.get('rsi') or 0.0
            score = analysis['score']

            signal = {
                'ticker': ticker,
                'price': analysis['current_price'],
                'trend': analysis['trend'],
                'rsi': round(float(rsi), 1),
                'score': score,
                'suggestion': _SUGGESTION_MAP.get(score, '觀察等待'),
            }

            if rsi < 30 and analysis['trend'] == 'BULLISH':
                signal['action'] = '強烈買入'
            elif rsi < 40:
                signal['action'] = '考慮買入'
            elif rsi > 70:
                signal['action'] = '考慮賣出'
            else:
                signal['action'] = '觀望'

            signals.append(signal)
        except Exception as e:
            logger.error(f'Signal error: {ticker} {e}')

    logger.info(f'Signals generated: {len(signals)}')
    return jsonify({'signals': signals, 'timestamp': datetime.now().isoformat()})


# ---------------------------------------------------------------------------
# 交易統計
# ---------------------------------------------------------------------------

@app.route('/api/trades/analysis')
def trades_analysis():
    trades = _load_all_trades()
    if not trades:
        return jsonify({'message': 'No trades'})

    buy_trades = [t for t in trades if t.get('action', '').lower() == 'buy']
    sell_trades = [t for t in trades if t.get('action', '').lower() == 'sell']

    ticker_stats: dict = {}
    for trade in trades:
        ticker = trade.get('ticker', '').upper()
        if ticker not in ticker_stats:
            ticker_stats[ticker] = {'buy': 0, 'sell': 0, 'total': 0}
        action = trade.get('action', '').lower()
        if action in ticker_stats[ticker]:
            ticker_stats[ticker][action] += 1
        ticker_stats[ticker]['total'] += 1

    recent = sorted(trades, key=lambda x: x.get('created_at', ''), reverse=True)[:5]
    logger.info(f'Trades analysis: {len(trades)} trades')

    return jsonify({
        'total_trades': len(trades),
        'buy_count': len(buy_trades),
        'sell_count': len(sell_trades),
        'by_ticker': ticker_stats,
        'recent_trades': recent,
        'timestamp': datetime.now().isoformat()
    })


# ---------------------------------------------------------------------------
# UI 靜態頁面
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    index_path = UI_DIR / 'index.html'
    if index_path.exists():
        return index_path.read_text(encoding='utf-8')
    return '<h1>NoFOMO</h1><p>UI not found</p>'


@app.route('/jobs')
def jobs():
    jobs_path = Path(__file__).parent.parent / 'ui' / 'jobs.html'
    if jobs_path.exists():
        return jobs_path.read_text(encoding='utf-8')
    return '<h1>Jobs</h1><p>Not found</p>'


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
