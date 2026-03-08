"""
交易邏輯測試 (Portfolio)
"""
import pytest
import json
import os
import tempfile
import shutil
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, patch, mock_open
import pandas as pd


# Create a temporary directory for test data
@pytest.fixture
def temp_data_dir():
    """建立臨時測試目錄"""
    temp_dir = tempfile.mkdtemp()
    yield Path(temp_dir)
    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_trades_dir(temp_data_dir):
    """建立臨時交易記錄目錄"""
    trades_dir = temp_data_dir / 'trades'
    trades_dir.mkdir(parents=True)
    return trades_dir


@pytest.fixture
def temp_portfolio_file(temp_data_dir):
    """建立臨時投資組合檔案"""
    return temp_data_dir / 'portfolio.json'


@pytest.fixture
def mock_portfolio_env(temp_data_dir, temp_trades_dir, temp_portfolio_file):
    """Mock 環境變數"""
    with patch('src.portfolio.DATA_DIR', temp_data_dir), \
         patch('src.portfolio.TRADES_DIR', temp_trades_dir), \
         patch('src.portfolio.PORTFOLIO_FILE', temp_portfolio_file):
        yield {
            'data_dir': temp_data_dir,
            'trades_dir': temp_trades_dir,
            'portfolio_file': temp_portfolio_file
        }


@pytest.fixture
def sample_trade():
    """範例交易資料"""
    return {
        'ticker': 'AAPL',
        'action': 'BUY',
        'quantity': 10,
        'entry_price': 150.0,
        'date': '2024-01-15'
    }


class TestGetTrades:
    """取得交易記錄測試"""
    
    def test_get_trades_empty(self, mock_portfolio_env):
        """空交易記錄"""
        from src.portfolio import get_trades
        result = get_trades()
        assert result == []
    
    def test_get_trades_with_data(self, mock_portfolio_env, temp_trades_dir):
        """有交易記錄"""
        # Create test trade file
        trade_file = temp_trades_dir / '20240115_100000.json'
        trade_data = {
            'ticker': 'AAPL',
            'action': 'BUY',
            'quantity': 10,
            'entry_price': 150.0,
            'date': '2024-01-15'
        }
        trade_file.write_text(json.dumps(trade_data))
        
        from src.portfolio import get_trades
        result = get_trades()
        assert len(result) == 1
        assert result[0]['ticker'] == 'AAPL'
    
    def test_get_trades_sorted(self, mock_portfolio_env, temp_trades_dir):
        """測試排序（由新到舊）"""
        # Create multiple trades
        trades_data = [
            {'ticker': 'AAPL', 'date': '2024-01-10', 'action': 'BUY'},
            {'ticker': 'TSLA', 'date': '2024-01-20', 'action': 'BUY'},
            {'ticker': 'NVDA', 'date': '2024-01-15', 'action': 'BUY'},
        ]
        
        for i, data in enumerate(trades_data):
            trade_file = temp_trades_dir / f'2024011{i}_100000.json'
            trade_file.write_text(json.dumps(data))
        
        from src.portfolio import get_trades
        result = get_trades()
        dates = [t.get('date', '') for t in result]
        assert dates == sorted(dates, reverse=True)


class TestPortfolio:
    """投資組合測試"""
    
    def test_get_portfolio_empty(self, mock_portfolio_env, temp_portfolio_file):
        """空投資組合"""
        from src.portfolio import get_portfolio
        result = get_portfolio()
        assert result.get('positions', []) == []
        assert result.get('cash', 0) == 0
    
    def test_get_portfolio_with_data(self, mock_portfolio_env, temp_portfolio_file):
        """有投資組合資料"""
        portfolio_data = {
            'positions': [
                {'ticker': 'AAPL', 'quantity': 10, 'avg_price': 150.0}
            ],
            'cash': 5000
        }
        temp_portfolio_file.write_text(json.dumps(portfolio_data))
        
        from src.portfolio import get_portfolio
        result = get_portfolio()
        assert len(result['positions']) == 1
        assert result['cash'] == 5000
    
    def test_save_portfolio(self, mock_portfolio_env, temp_portfolio_file):
        """儲存投資組合"""
        from src.portfolio import save_portfolio, get_portfolio
        portfolio = {'positions': [], 'cash': 10000}
        save_portfolio(portfolio)
        
        result = get_portfolio()
        assert result['cash'] == 10000


class TestAddTrade:
    """新增交易測試"""
    
    def test_add_trade_creates_file(self, mock_portfolio_env, temp_trades_dir, sample_trade):
        """新增交易建立檔案"""
        from src.portfolio import add_trade, get_trades
        
        trade_id = add_trade(sample_trade)
        assert trade_id is not None
        
        # Check file exists
        trade_files = list(temp_trades_dir.glob('*.json'))
        assert len(trade_files) >= 1
    
    def test_add_trade_generates_id(self, mock_portfolio_env, sample_trade):
        """交易 ID 格式"""
        from src.portfolio import add_trade

        trade_id = add_trade(sample_trade)
        # Format: YYYYMMDD_HHMMSS_ffffff (含微秒，避免同秒衝突)
        assert len(trade_id) == 22
        assert trade_id.count('_') == 2
    
    def test_add_trade_has_timestamp(self, mock_portfolio_env, sample_trade, temp_trades_dir):
        """交易包含時間戳"""
        from src.portfolio import add_trade
        
        add_trade(sample_trade)
        
        # Find the created file
        trade_file = list(temp_trades_dir.glob('*.json'))[0]
        trade_data = json.loads(trade_file.read_text())
        
        assert 'created_at' in trade_data
        assert 'id' in trade_data


class TestUpdatePortfolio:
    """更新投資組合測試"""
    
    def test_update_portfolio_new_buy(self, mock_portfolio_env, temp_portfolio_file, sample_trade):
        """新買入建立部位"""
        from src.portfolio import update_portfolio, get_portfolio
        
        # Empty portfolio first
        temp_portfolio_file.write_text(json.dumps({'positions': [], 'cash': 0}))
        
        update_portfolio(sample_trade)
        portfolio = get_portfolio()
        
        assert len(portfolio['positions']) == 1
        assert portfolio['positions'][0]['ticker'] == 'AAPL'
        assert portfolio['positions'][0]['quantity'] == 10
    
    def test_update_portfolio_add_to_position(self, mock_portfolio_env, temp_portfolio_file):
        """加碼現有部位"""
        from src.portfolio import update_portfolio, get_portfolio
        
        # Setup existing position
        initial_portfolio = {
            'positions': [
                {'ticker': 'AAPL', 'quantity': 10, 'avg_price': 150.0}
            ],
            'cash': 0
        }
        temp_portfolio_file.write_text(json.dumps(initial_portfolio))
        
        # Add more
        additional_trade = {
            'ticker': 'AAPL',
            'action': 'BUY',
            'quantity': 10,
            'entry_price': 160.0
        }
        update_portfolio(additional_trade)
        
        portfolio = get_portfolio()
        aapl_position = [p for p in portfolio['positions'] if p['ticker'] == 'AAPL'][0]
        
        # Average price should be recalculated
        assert aapl_position['quantity'] == 20
        assert aapl_position['avg_price'] == 155.0  # (10*150 + 10*160) / 20
    
    def test_update_portfolio_sell_position(self, mock_portfolio_env, temp_portfolio_file):
        """賣出部位"""
        from src.portfolio import update_portfolio, get_portfolio
        
        # Setup existing position
        initial_portfolio = {
            'positions': [
                {'ticker': 'AAPL', 'quantity': 10, 'avg_price': 150.0}
            ],
            'cash': 0
        }
        temp_portfolio_file.write_text(json.dumps(initial_portfolio))
        
        # Sell
        sell_trade = {
            'ticker': 'AAPL',
            'action': 'SELL',
            'quantity': 5,
            'entry_price': 160.0
        }
        update_portfolio(sell_trade)
        
        portfolio = get_portfolio()
        aapl_position = [p for p in portfolio['positions'] if p['ticker'] == 'AAPL'][0]
        
        assert aapl_position['quantity'] == 5
    
    def test_update_portfolio_sell_all(self, mock_portfolio_env, temp_portfolio_file):
        """全部賣出移除部位"""
        from src.portfolio import update_portfolio, get_portfolio
        
        initial_portfolio = {
            'positions': [
                {'ticker': 'AAPL', 'quantity': 10, 'avg_price': 150.0}
            ],
            'cash': 0
        }
        temp_portfolio_file.write_text(json.dumps(initial_portfolio))
        
        sell_trade = {
            'ticker': 'AAPL',
            'action': 'SELL',
            'quantity': 10,
            'entry_price': 160.0
        }
        update_portfolio(sell_trade)
        
        portfolio = get_portfolio()
        aapl_positions = [p for p in portfolio['positions'] if p.get('ticker') == 'AAPL']
        
        assert len(aapl_positions) == 0


class TestCalculatePnL:
    """損益計算測試"""
    
    def test_calculate_pnl_empty(self, mock_portfolio_env):
        """無交易記錄"""
        from src.portfolio import calculate_pnl
        result = calculate_pnl()
        
        assert result['realized_pnl'] == 0
        assert result['unrealized_pnl'] == 0
        assert result['total_pnl'] == 0
    
    def test_calculate_realized_pnl(self, mock_portfolio_env, temp_trades_dir):
        """已實現損益計算（平均成本法：先買後賣）"""
        # 先買入，建立成本基礎
        buy_file = temp_trades_dir / '20240115_090000.json'
        buy_file.write_text(json.dumps({
            'ticker': 'AAPL',
            'action': 'BUY',
            'quantity': 10,
            'entry_price': 150.0,
            'date': '2024-01-15'
        }))

        # 再以 160 賣出
        sell_file = temp_trades_dir / '20240115_100000.json'
        sell_file.write_text(json.dumps({
            'ticker': 'AAPL',
            'action': 'SELL',
            'quantity': 10,
            'entry_price': 160.0,
            'date': '2024-01-15'
        }))

        from src.portfolio import calculate_pnl
        result = calculate_pnl()

        # 已實現損益：(160 - 150) * 10 = 100
        assert result['realized_pnl'] == 100.0


class TestAnalyzeErrors:
    """錯誤分析測試"""
    
    def test_analyze_errors_empty(self, mock_portfolio_env):
        """無錯誤"""
        from src.portfolio import analyze_errors
        result = analyze_errors()
        assert result == []
    
    def test_analyze_errors_finds_low_score(self, mock_portfolio_env, temp_trades_dir):
        """找出低評分交易"""
        trade_file = temp_trades_dir / '20240115_100000.json'
        trade_data = {
            'ticker': 'AAPL',
            'action': 'BUY',
            'score': 2  # Low score
        }
        trade_file.write_text(json.dumps(trade_data))
        
        from src.portfolio import analyze_errors
        result = analyze_errors()
        
        assert len(result) == 1
    
    def test_analyze_errors_ignores_high_score(self, mock_portfolio_env, temp_trades_dir):
        """忽略高評分交易"""
        trade_file = temp_trades_dir / '20240115_100000.json'
        trade_data = {
            'ticker': 'AAPL',
            'action': 'BUY',
            'score': 4  # High score
        }
        trade_file.write_text(json.dumps(trade_data))
        
        from src.portfolio import analyze_errors
        result = analyze_errors()
        
        assert len(result) == 0


class TestTradeValidation:
    """交易驗證測試"""
    
    def test_trade_with_minimal_data(self, mock_portfolio_env):
        """最簡交易資料"""
        from src.portfolio import add_trade
        
        trade = {
            'ticker': 'TSLA',
            'action': 'BUY',
            'quantity': 5,
            'entry_price': 200.0
        }
        
        trade_id = add_trade(trade)
        assert trade_id is not None


class TestPortfolioMultiPosition:
    """多部位投資組合測試"""
    
    def test_multiple_positions(self, mock_portfolio_env, temp_portfolio_file):
        """多個不同標的"""
        portfolio = {
            'positions': [
                {'ticker': 'AAPL', 'quantity': 10, 'avg_price': 150.0},
                {'ticker': 'TSLA', 'quantity': 5, 'avg_price': 200.0},
                {'ticker': 'NVDA', 'quantity': 3, 'avg_price': 500.0}
            ],
            'cash': 1000
        }
        temp_portfolio_file.write_text(json.dumps(portfolio))
        
        from src.portfolio import get_portfolio
        result = get_portfolio()
        
        assert len(result['positions']) == 3
    
    def test_position_lookup(self, mock_portfolio_env, temp_portfolio_file):
        """部位查詢"""
        portfolio = {
            'positions': [
                {'ticker': 'AAPL', 'quantity': 10, 'avg_price': 150.0},
                {'ticker': 'TSLA', 'quantity': 5, 'avg_price': 200.0}
            ],
            'cash': 1000
        }
        temp_portfolio_file.write_text(json.dumps(portfolio))
        
        from src.portfolio import get_portfolio
        result = get_portfolio()
        
        aapl = next((p for p in result['positions'] if p['ticker'] == 'AAPL'), None)
        assert aapl is not None
        assert aapl['quantity'] == 10


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
