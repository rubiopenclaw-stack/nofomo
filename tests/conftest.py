"""
Pytest 配置與共用 fixtures
"""
import pytest
import pandas as pd
import numpy as np
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime, timedelta


@pytest.fixture
def mock_yfinance():
    """Mock yfinance 模組"""
    with patch('src.analyzer.yf') as mock_yf:
        yield mock_yf


@pytest.fixture
def sample_stock_data():
    """產生標準測試用股票數據 (含漲跌)"""
    dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
    # 產生有波動的價格數據，確保 RSI 計算有意義
    np.random.seed(42)
    close_prices = 100 + np.cumsum(np.random.randn(30) * 2)
    
    df = pd.DataFrame({
        'Open': close_prices * 0.99,
        'High': close_prices * 1.02,
        'Low': close_prices * 0.98,
        'Close': close_prices,
        'Volume': np.random.randint(1000000, 5000000, 30)
    }, index=dates)
    return df


@pytest.fixture
def flat_price_data():
    """價格完全持平的數據（測試 RSI 除零）"""
    dates = pd.date_range(end=datetime.now(), periods=20, freq='D')
    df = pd.DataFrame({
        'Open': [100.0] * 20,
        'High': [100.0] * 20,
        'Low': [100.0] * 20,
        'Close': [100.0] * 20,  # 完全持平
        'Volume': [1000000] * 20
    }, index=dates)
    return df


@pytest.fixture
def monotonic_up_data():
    """單調上漲數據（測試 RSI loss=0 邊界）"""
    dates = pd.date_range(end=datetime.now(), periods=20, freq='D')
    df = pd.DataFrame({
        'Open': np.linspace(100, 120, 20),
        'High': np.linspace(101, 121, 20),
        'Low': np.linspace(99, 119, 20),
        'Close': np.linspace(100, 120, 20),  # 持續上漲，loss 會是 0
        'Volume': [1000000] * 20
    }, index=dates)
    return df


@pytest.fixture
def monotonic_down_data():
    """單調下跌數據（測試 RSI gain=0 邊界）"""
    dates = pd.date_range(end=datetime.now(), periods=20, freq='D')
    df = pd.DataFrame({
        'Open': np.linspace(120, 100, 20),
        'High': np.linspace(121, 101, 20),
        'Low': np.linspace(119, 99, 20),
        'Close': np.linspace(120, 100, 20),  # 持續下跌，gain 會是 0
        'Volume': [1000000] * 20
    }, index=dates)
    return df


@pytest.fixture
def empty_dataframe():
    """空 DataFrame"""
    return pd.DataFrame()


@pytest.fixture
def dataframe_without_close():
    """沒有 Close 欄位的 DataFrame"""
    return pd.DataFrame({
        'Open': [100, 101, 102],
        'High': [102, 103, 104],
        'Low': [98, 99, 100],
        'Volume': [1000000, 1100000, 1200000]
    })
