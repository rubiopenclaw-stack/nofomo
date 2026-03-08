"""
API 端點測試
"""
import pytest
import json
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime
import pandas as pd
import numpy as np


# Mock yfinance before importing app
@pytest.fixture
def mock_yfinance_api():
    """Mock yfinance for API tests"""
    with patch('src.api.yf') as mock_yf:
        # Create mock ticker
        mock_ticker = MagicMock()
        
        # Mock history for price
        hist_df = pd.DataFrame({
            'Close': [150.0, 151.0, 152.0],
            'Open': [149.0, 150.0, 151.0],
            'High': [152.0, 153.0, 154.0],
            'Low': [148.0, 149.0, 150.0],
            'Volume': [1000000, 1100000, 1200000]
        }, index=pd.date_range(end=datetime.now(), periods=3))
        
        mock_ticker.history.return_value = hist_df
        
        # Mock info
        mock_ticker.info = {
            'currency': 'USD',
            'fiftyTwoWeekLow': 100.0,
            'fiftyTwoWeekHigh': 200.0,
            'shortName': 'Apple Inc.',
            'volume': 1000000
        }
        
        mock_yf.Ticker.return_value = mock_ticker
        yield mock_yf


@pytest.fixture
def app_client(mock_yfinance_api):
    """Create test client for Flask app"""
    from src.api import app
    app.config['TESTING'] = True
    with app.test_client() as client:
        # Clear cache before each test
        from src.api import _price_cache
        _price_cache.clear()
        yield client


class TestHealthEndpoint:
    """健康檢查端點測試"""
    
    def test_health_ok(self, app_client):
        """正常健康檢查"""
        response = app_client.get('/api/health')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['status'] == 'ok'
        assert 'timestamp' in data
        assert 'cache_size' in data
    
    def test_health_has_cache_info(self, app_client):
        """健康檢查包含快取資訊"""
        response = app_client.get('/api/health')
        data = json.loads(response.data)
        assert 'cache_ttl' in data
        assert 'watchlist_count' in data


class TestQuoteEndpoint:
    """報價端點測試"""
    
    def test_quote_valid_ticker(self, app_client):
        """正常報價查詢"""
        response = app_client.get('/api/quote?ticker=AAPL')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert data['ticker'] == 'AAPL'
        assert 'current_price' in data
    
    def test_quote_missing_ticker(self, app_client):
        """缺少 ticker 參數"""
        response = app_client.get('/api/quote')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_quote_uppercase_ticker(self, app_client):
        """大寫 ticker 自動轉換"""
        response = app_client.get('/api/quote?ticker=aapl')
        data = json.loads(response.data)
        assert data['ticker'] == 'AAPL'
    
    def test_quote_cache(self, app_client):
        """測試快取機制"""
        # First request
        response1 = app_client.get('/api/quote?ticker=MSFT')
        data1 = json.loads(response1.data)
        
        # Second request should hit cache
        response2 = app_client.get('/api/quote?ticker=MSFT')
        data2 = json.loads(response2.data)
        
        assert data1['current_price'] == data2['current_price']


class TestAnalyzeEndpoint:
    """分析端點測試"""
    
    def test_analyze_valid_ticker(self, app_client):
        """正常分析查詢"""
        response = app_client.get('/api/analyze?ticker=AAPL')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'current_price' in data
        assert 'rsi' in data
        assert 'score' in data
    
    def test_analyze_missing_ticker(self, app_client):
        """缺少 ticker"""
        response = app_client.get('/api/analyze')
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_analyze_has_recommendation(self, app_client):
        """分析包含建議"""
        response = app_client.get('/api/analyze?ticker=AAPL')
        data = json.loads(response.data)
        assert 'suggestion' in data
        assert 'stop_loss' in data
        assert 'target_1' in data
        assert 'target_2' in data
    
    def test_analyze_has_technical_indicators(self, app_client):
        """分析包含技術指標"""
        response = app_client.get('/api/analyze?ticker=AAPL')
        data = json.loads(response.data)
        assert 'ma5' in data
        assert 'ma20' in data
        assert 'macd' in data
        assert 'bollinger' in data


class TestBatchQuoteEndpoint:
    """批量報價端點測試"""
    
    def test_batch_quote_valid(self, app_client):
        """正常批量報價"""
        response = app_client.get('/api/batch-quote?tickers=AAPL,MSFT,GOOGL')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'AAPL' in data
        assert 'MSFT' in data
        assert 'GOOGL' in data
    
    def test_batch_quote_empty(self, app_client):
        """空 ticker 清單"""
        response = app_client.get('/api/batch-quote')
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_batch_quote_limit(self, app_client):
        """超過數量限制"""
        # 20 個以內應該可以
        tickers = ','.join([f'TICKER{i}' for i in range(20)])
        response = app_client.get(f'/api/batch-quote?tickers={tickers}')
        # 這個會因為無效 ticker 返回 error 但不超過限制
    
    def test_batch_quote_too_many(self, app_client):
        """超過 20 個限制"""
        tickers = ','.join([f'TICKER{i}' for i in range(21)])
        response = app_client.get(f'/api/batch-quote?tickers={tickers}')
        data = json.loads(response.data)
        assert 'error' in data


class TestWatchlistEndpoint:
    """關注清單端點測試"""
    
    def test_get_watchlist(self, app_client):
        """取得關注清單"""
        response = app_client.get('/api/watchlist')
        data = json.loads(response.data)
        assert 'watchlist' in data
        assert len(data['watchlist']) > 0
    
    def test_update_watchlist(self, app_client):
        """更新關注清單"""
        new_watchlist = ['AAPL', 'TSLA', 'NVDA']
        response = app_client.post(
            '/api/watchlist',
            data=json.dumps({'watchlist': new_watchlist}),
            content_type='application/json'
        )
        data = json.loads(response.data)
        assert data['success'] is True


class TestHistoryEndpoint:
    """歷史數據端點測試"""
    
    def test_history_valid(self, app_client):
        """正常歷史數據"""
        response = app_client.get('/api/history?ticker=AAPL&period=1mo')
        data = json.loads(response.data)
        assert 'data' in data
        assert 'ticker' in data
        assert data['period'] == '1mo'
    
    def test_history_missing_ticker(self, app_client):
        """缺少 ticker"""
        response = app_client.get('/api/history?period=1mo')
        data = json.loads(response.data)
        assert 'error' in data
    
    def test_history_invalid_period(self, app_client):
        """無效週期"""
        response = app_client.get('/api/history?ticker=AAPL&period=invalid')
        data = json.loads(response.data)
        assert 'error' in data


class TestCacheEndpoint:
    """快取端點測試"""
    
    def test_clear_cache(self, app_client):
        """清除快取"""
        # 先建立一些快取
        app_client.get('/api/quote?ticker=AAPL')
        
        # 清除
        response = app_client.post('/api/cache/clear')
        data = json.loads(response.data)
        assert data['success'] is True


class TestTradesEndpoint:
    """交易記錄端點測試"""
    
    def test_get_trades(self, app_client):
        """取得交易記錄"""
        response = app_client.get('/api/trades')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert isinstance(data, list)
    
    def test_add_trade(self, app_client):
        """新增交易記錄"""
        trade_data = {
            'ticker': 'AAPL',
            'action': 'buy',
            'quantity': 10,
            'entry_price': 150.0,
            'date': '2024-01-15'
        }
        response = app_client.post(
            '/api/trades',
            data=json.dumps(trade_data),
            content_type='application/json'
        )
        data = json.loads(response.data)
        assert data['success'] is True
        assert 'id' in data


class TestPortfolioEndpoint:
    """投資組合端點測試"""
    
    def test_get_portfolio(self, app_client):
        """取得投資組合"""
        response = app_client.get('/api/portfolio')
        assert response.status_code == 200
        data = json.loads(response.data)
        assert 'positions' in data
    
    def test_portfolio_summary(self, app_client):
        """投資組合摘要"""
        response = app_client.get('/api/portfolio/summary')
        data = json.loads(response.data)
        assert 'cash' in data
        assert 'stock_value' in data
        assert 'total_assets' in data
    
    def test_portfolio_performance(self, app_client):
        """投資組合績效"""
        response = app_client.get('/api/portfolio/performance')
        data = json.loads(response.data)
        assert 'positions' in data
        assert 'total_value' in data


class TestAlertsEndpoint:
    """價格提醒端點測試"""
    
    def test_get_alerts(self, app_client):
        """取得提醒"""
        response = app_client.get('/api/alerts')
        data = json.loads(response.data)
        assert 'alerts' in data
    
    def test_set_alert(self, app_client):
        """設定提醒"""
        alert_data = {
            'ticker': 'AAPL',
            'target_price': 200.0,
            'condition': 'above'
        }
        response = app_client.post(
            '/api/alerts',
            data=json.dumps(alert_data),
            content_type='application/json'
        )
        data = json.loads(response.data)
        assert data['success'] is True
    
    def test_clear_alerts(self, app_client):
        """清除提醒"""
        response = app_client.delete('/api/alerts')
        data = json.loads(response.data)
        assert data['success'] is True


class TestSignalsEndpoint:
    """交易訊號端點測試"""
    
    def test_get_signals(self, app_client):
        """取得交易訊號"""
        response = app_client.get('/api/signals')
        data = json.loads(response.data)
        assert 'signals' in data
        assert 'timestamp' in data


class TestRiskEndpoint:
    """風險評估端點測試"""
    
    def test_risk_assessment(self, app_client):
        """風險評估"""
        response = app_client.get('/api/risk评估')
        data = json.loads(response.data)
        assert 'risk_level' in data
        assert 'risk_score' in data


class TestTradesAnalysisEndpoint:
    """交易分析端點測試"""
    
    def test_trades_analysis(self, app_client):
        """交易分析"""
        response = app_client.get('/api/trades/analysis')
        data = json.loads(response.data)
        assert 'total_trades' in data


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
