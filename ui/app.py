"""
NoFOMO - 股票交易記錄 Web App
"""

import streamlit as st
import json
from pathlib import Path
from datetime import datetime
import sys

sys.path.insert(0, str(Path(__file__).parent.parent / 'src'))

from portfolio import get_trades, get_portfolio, add_trade, calculate_pnl
from analyzer import get_stock_price, technical_analysis, generate_suggestion

# 頁面配置
st.set_page_config(
    page_title="📈 NoFOMO - 股票交易記錄",
    page_icon="📈",
    layout="wide"
)

# CSS
st.markdown("""
<style>
    .main-title {
        font-size: 2rem;
        font-weight: 700;
        color: #1E3A5F;
    }
    .trade-card {
        background: #F8FAFC;
        border-radius: 12px;
        padding: 16px;
        margin: 8px 0;
        border-left: 4px solid #4F46E5;
    }
    .buy { border-left-color: #10B981; }
    .sell { border-left-color: #EF4444; }
    .score-5 { color: #10B981; }
    .score-4 { color: #22C55E; }
    .score-3 { color: #EAB308; }
    .score-2 { color: #F97316; }
    .score-1 { color: #EF4444; }
</style>
""", unsafe_allow_html=True)

st.markdown('<p class="main-title">📈 NoFOMO 股票交易記錄</p>', unsafe_allow_html=True)
st.markdown("記錄每一筆交易，持續優化你的操作策略")
st.markdown("---")

# 分頁
tab1, tab2, tab3, tab4 = st.tabs(["💬 交易記錄", "📊 持倉", "🔍 股票分析", "📈 資產"])

# ========== Tab 1: 交易記錄 ==========
with tab1:
    col1, col2 = st.columns([1, 2])
    
    with col1:
        st.subheader("➕ 新增交易")
        
        with st.form("trade_form"):
            ticker = st.text_input("股票代號", placeholder="例如: AAPL, TSMC, 2330.TW").upper()
            action = st.selectbox("買賣方向", ["BUY", "SELL"])
            price = st.number_input("成交價格", min_value=0.0, step=0.01)
            quantity = st.number_input("股數", min_value=1, step=1)
            reason = st.text_area("交易理由", placeholder="為什麼買/賣?")
            
            submitted = st.form_submit_button("💾 記錄交易")
            
            if submitted and ticker and price and quantity:
                # 取得即時股價
                current_price = price  # 使用成交價
                stock_info = get_stock_price(ticker)
                
                # 技術分析
                analysis = technical_analysis(ticker)
                suggestion = generate_suggestion(analysis, price)
                
                # 記錄
                trade = {
                    'date': datetime.now().strftime('%Y-%m-%d %H:%M'),
                    'ticker': ticker,
                    'action': action,
                    'entry_price': price,
                    'quantity': quantity,
                    'total_value': price * quantity,
                    'current_price': stock_info.get('current_price', price),
                    'reason': reason,
                    'score': analysis.get('score', 3),
                    'rating': suggestion.get('rating', '⭐⭐⭐'),
                    'suggestion': suggestion.get('suggestion', ''),
                    'stop_loss': suggestion.get('stop_loss'),
                    'target_1': suggestion.get('target_1'),
                    'target_2': suggestion.get('target_2'),
                    'rsi': analysis.get('rsi'),
                    'trend': analysis.get('trend'),
                    'status': 'HOLDING' if action == 'BUY' else 'CLOSED'
                }
                
                trade_id = add_trade(trade)
                st.success(f"✅ 交易已記錄! ID: {trade_id}")
    
    with col2:
        st.subheader("📝 交易歷史")
        
        trades = get_trades trades:
            for()
        
        if trade in trades[:20]:
                with st.expander(f"{trade['date']} | {trade['ticker']} | {trade['action']} @ {trade['entry_price']}"):
                    col_a, col_b = st.columns(2)
                    
                    with col_a:
                        st.write(f"**股數:** {trade['quantity']}")
                        st.write(f"**總值:** ${trade['total_value']:,.0f}")
                        st.write(f"**理由:** {trade.get('reason', '-')}")
                    
                    with col_b:
                        score = trade.get('score', 3)
                        st.write(f"**評分:** {trade.get('rating', '⭐')}")
                        st.write(f"**RSI:** {trade.get('rsi', '-'):.1f}" if trade.get('rsi') else "**RSI:** -")
                        st.write(f"**趨勢:** {trade.get('trend', '-')}")
                    
                    if trade.get('stop_loss'):
                        st.write(f"🛡️ 停損: ${trade['stop_loss']}")
                    if trade.get('target_1'):
                        st.write(f"🎯 目標1: ${trade['target_1']}")
        else:
            st.info("尚無交易記錄")

# ========== Tab 2: 持倉 ==========
with tab2:
    st.subheader("📊 目前持倉")
    
    portfolio = get_portfolio()
    positions = portfolio.get('positions', [])
    
    if positions:
        for pos in positions:
            # 取得即時股價
            stock = get_stock_price(pos['ticker'])
            current = stock.get('current_price', 0)
            avg = pos.get('avg_price', 0)
            
            pnl = (current - avg) * pos['quantity'] if current else 0
            pnl_pct = ((current - avg) / avg * 100) if avg and current else 0
            
            with st.container():
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.write(f"**{pos['ticker']}**")
                    st.caption(f"均價: ${avg:.2f}")
                
                with col2:
                    st.write(f"**{pos['quantity']} 股**")
                    st.caption(f"市值: ${current * pos['quantity']:,.0f}" if current else "-")
                
                with col3:
                    color = "green" if pnl >= 0 else "red"
                    st.markdown(f":{color}[${pnl:,.0f}]")
                    st.caption(f"{pnl_pct:.1f}%")
                
                with col4:
                    if stock.get('current_price'):
                        st.write(f"現價: ${current:.2f}")
                    else:
                        st.write("無法取得報價")
    else:
        st.info("目前無持股")

# ========== Tab 3: 股票分析 ==========
with tab3:
    st.subheader("🔍 股票技術分析")
    
    search_ticker = st.text_input("輸入股票代號", placeholder="例如: AAPL, TSMC").upper()
    
    if st.button("🔎 分析") and search_ticker:
        with st.spinner("分析中..."):
            # 股價
            stock = get_stock_price(search_ticker)
            
            if 'error' not in stock:
                st.success(f"{stock.get('name', search_ticker)} 現價: ${stock.get('current_price', 'N/A')}")
                
                # 技術分析
                analysis = technical_analysis(search_ticker)
                suggestion = generate_suggestion(analysis)
                
                # 顯示結果
                col1, col2, col3, col4 = st.columns(4)
                
                with col1:
                    st.metric("評分", suggestion.get('rating', '-'))
                with col2:
                    st.metric("RSI", f"{analysis.get('rsi', 0):.1f}" if analysis.get('rsi') else "-")
                with col3:
                    st.metric("趨勢", analysis.get('trend', '-'))
                with col4:
                    st.metric("MA20", f"${analysis.get('ma20', 0):.2f}" if analysis.get('ma20') else "-")
                
                # 建議
                st.subheader("💡 建議")
                
                col_a, col_b, col_c = st.columns(3)
                with col_a:
                    st.info(f"**買入建議:** {suggestion.get('suggestion', '-')}")
                with col_b:
                    if suggestion.get('stop_loss'):
                        st.warning(f"🛡️ 停損: ${suggestion['stop_loss']}")
                with col_c:
                    if suggestion.get('target_1'):
                        st.success(f"🎯 目標1: ${suggestion['target_1']}")
                
                # 詳細指標
                with st.expander("📊 詳細技術指標"):
                    st.write(f"MA5: ${analysis.get('ma5', 0):.2f}" if analysis.get('ma5') else "MA5: -")
                    st.write(f"MA20: ${analysis.get('ma20', 0):.2f}" if analysis.get('ma20') else "MA20: -")
                    st.write(f"MA60: ${analysis.get('ma60', 0):.2f}" if analysis.get('ma60') else "MA60: -")
                    
                    macd = analysis.get('macd', {})
                    if macd.get('macd'):
                        st.write(f"MACD: {macd['macd']:.4f} (Signal: {macd['signal']:.4f})")
                        st.write(f"MACD 交叉: {macd.get('crossover', '-')}")
                    
                    bb = analysis.get('bollinger', {})
                    if bb:
                        st.write(f"布林通道: Upper ${bb.get('upper', 0):.2f}, Lower ${bb.get('lower', 0):.2f}")
            else:
                st.error(f"無法取得 {search_ticker} 的資料")

# ========== Tab 4: 資產 ==========
with tab4:
    st.subheader("📈 資產總覽")
    
    pnl = calculate_pnl()
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        st.metric("已實現損益", f"${pnl.get('realized_pnl', 0):,.0f}")
    with col2:
        st.metric("未實現損益", f"${pnl.get('unrealized_pnl', 0):,.0f}")
    with col3:
        st.metric("總損益", f"${pnl.get('total_pnl', 0):,.0f}")
    
    # 統計
    trades = get_trades()
    buy_count = sum(1 for t in trades if t.get('action') == 'BUY')
    sell_count = sum(1 for t in trades if t.get('action') == 'SELL')
    
    col_a, col_b = st.columns(2)
    with col_a:
        st.write(f"**買入次數:** {buy_count}")
    with col_b:
        st.write(f"**賣出次數:** {sell_count}")

# 底部
st.markdown("---")
st.caption(f"NoFOMO v1.0 | 最後更新: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
