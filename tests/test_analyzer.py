"""
analyzer.py 單元測試
"""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock
from src.analyzer import (
    calculate_rsi,
    calculate_macd,
    calculate_ma,
    calculate_bollinger,
    get_stock_history,
)


class TestCalculateRSI:
    """RSI 計算測試"""
    
    def test_normal_rsi(self, sample_stock_data):
        """正常 RSI 計算"""
        result = calculate_rsi(sample_stock_data)
        assert result is not None
        assert 0 <= result <= 100
    
    def test_empty_dataframe(self, empty_dataframe):
        """空 DataFrame 處理"""
        result = calculate_rsi(empty_dataframe)
        assert result is None
    
    def test_no_close_column(self, dataframe_without_close):
        """沒有 Close 欄位"""
        result = calculate_rsi(dataframe_without_close)
        assert result is None
    
    def test_zero_loss_divzero_protection(self, monotonic_up_data):
        """邊界測試：單調上漲導致 loss=0（除零防護）"""
        # 單調上漲時，loss 應該是 0，rs = gain/0 = inf，RSI = 100
        result = calculate_rsi(monotonic_up_data)
        assert result is not None
        assert result == 100.0  # 應該安全地返回 100
    
    def test_zero_gain_divzero_protection(self, monotonic_down_data):
        """邊界測試：單調下跌導致 gain=0（除零防護）"""
        # 單調下跌時，gain 應該是 0，rs = 0/loss = 0，RSI = 0
        result = calculate_rsi(monotonic_down_data)
        assert result is not None
        assert result == 0.0  # 應該安全地返回 0
    
    def test_flat_price_no_divzero(self, flat_price_data):
        """邊界測試：價格完全持平"""
        result = calculate_rsi(flat_price_data)
        # 持平時 gain=loss=0，rs = 0/0 = nan，應返回 NaN 或做特殊處理
        # 檢查不會崩潰
        assert result is None or (isinstance(result, float) and np.isnan(result))


class TestCalculateMACD:
    """MACD 計算測試"""
    
    def test_normal_macd(self, sample_stock_data):
        """正常 MACD 計算"""
        result = calculate_macd(sample_stock_data)
        assert 'macd' in result
        assert 'signal' in result
        assert 'histogram' in result
        assert 'crossover' in result
        assert result['macd'] is not None
    
    def test_empty_dataframe(self, empty_dataframe):
        """空 DataFrame 處理"""
        result = calculate_macd(empty_dataframe)
        assert result['macd'] is None
        assert result['signal'] is None
        assert result['histogram'] is None
    
    def test_no_close_column(self, dataframe_without_close):
        """沒有 Close 欄位"""
        result = calculate_macd(dataframe_without_close)
        assert result['macd'] is None
        assert result['signal'] is None
        assert result['histogram'] is None
    
    def test_flat_price(self, flat_price_data):
        """價格完全持平"""
        result = calculate_macd(flat_price_data)
        # 持平時 MACD 應該趨近 0
        assert result['macd'] is not None
        assert abs(result['macd']) < 1e-10
    
    def test_crossover_detection(self, sample_stock_data):
        """黃金交叉/死亡交叉偵測"""
        result = calculate_macd(sample_stock_data)
        assert result['crossover'] in ['GOLDEN', 'DEAD', 'NEUTRAL']


class TestCalculateMA:
    """移動平均線測試"""
    
    def test_normal_ma(self, sample_stock_data):
        """正常 MA 計算"""
        result = calculate_ma(sample_stock_data, period=5)
        assert result is not None
        assert result > 0
    
    def test_empty_dataframe(self, empty_dataframe):
        """空 DataFrame"""
        result = calculate_ma(empty_dataframe)
        assert result is None
    
    def test_no_close_column(self, dataframe_without_close):
        """沒有 Close 欄位"""
        result = calculate_ma(dataframe_without_close)
        assert result is None
    
    def test_period_larger_than_data(self, sample_stock_data):
        """週期大於數據長度"""
        result = calculate_ma(sample_stock_data, period=100)
        # 數據不足時應返回 NaN 或 None
        assert result is None or (isinstance(result, float) and np.isnan(result))


class TestCalculateBollinger:
    """布林通道測試"""
    
    def test_normal_bollinger(self, sample_stock_data):
        """正常布林通道計算"""
        result = calculate_bollinger(sample_stock_data)
        assert 'upper' in result
        assert 'middle' in result
        assert 'lower' in result
        assert 'position' in result
        assert result['upper'] > result['middle'] > result['lower']
    
    def test_empty_dataframe(self, empty_dataframe):
        """空 DataFrame"""
        result = calculate_bollinger(empty_dataframe)
        assert result == {}
    
    def test_no_close_column(self, dataframe_without_close):
        """沒有 Close 欄位"""
        result = calculate_bollinger(dataframe_without_close)
        assert result == {}


class TestGetStockHistory:
    """股票歷史數據測試"""
    
    def test_get_history_mock(self, mock_yfinance):
        """Mock yfinance 獲取歷史數據"""
        # 設定 mock
        mock_ticker = Mock()
        mock_ticker.history.return_value = pd.DataFrame({
            'Close': [100, 101, 102]
        })
        mock_yfinance.Ticker.return_value = mock_ticker
        
        result = get_stock_history('AAPL')
        assert not result.empty
        assert 'Close' in result.columns


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
