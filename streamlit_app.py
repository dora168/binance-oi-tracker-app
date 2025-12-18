import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
from io import StringIO

# ================= 核心配置区 =================
DATA_SOURCE = "http://43.156.132.4:8080/oi_analysis.csv"
# ============================================

def format_money(num):
    try:
        num = float(num)
        if num >= 1_000_000_000: return f"{num/1_000_000_000:.2f}B"
        if num >= 1_000_000: return f"{num/1_000_000:.2f}M"
        if num >= 1_000: return f"{num/1_000:.0f}K"
        return f"{num:.0f}"
    except:
        return str(num)

def load_data(url):
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200: return pd.DataFrame()
        try:
            content = response.content.decode('utf-8-sig')
        except:
            content = response.content.decode('gbk')
        return pd.read_csv(StringIO(content))
    except:
        return pd.DataFrame()

def render_tradingview_widget(symbol, height=580):
    """
    高度提升至 580px，并优化了指标加载逻辑
    """
    clean_symbol = symbol.upper().strip()
    tv_symbol = f"BINANCE:{clean_symbol}.P"
    container_id = f"tv_{clean_symbol}"

    html_code = f"""
    <div class="tradingview-widget-container" style="height: {height}px; width: 100%; border: 1px solid #eee; border-radius: 8px; overflow: hidden;">
      <div id="{container_id}" style="height: 100%; width: 100%;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
        "autosize": true,
        "symbol": "{tv_symbol}",
        "interval": "60",
        "timezone": "Asia/Shanghai",
        "theme": "light",
        "style": "1",
        "locale": "zh_CN",
        "toolbar_bg": "#f1f3f6",
        "enable_publishing": false,
        "hide_top_toolbar": true,
        "hide_legend": false,
        "save_image": false,
        "container_id": "{container_id}",
        "studies": [
            "MASimple@tv-basicstudies",     
            "STD;Fund_crypto_open_interest",
            "STD;Fund_long_short_ratio"
        ],
        "disabled_features": [
            "header_symbol_search", 
            "header_compare", 
            "use_localstorage_for_settings", 
            "timeframes_toolbar", 
            "volume_force_overlay"
        ],
        "overrides": {{
            "paneProperties.topMargin": 10,
            "paneProperties.bottomMargin": 5
        }}
      }}
      );
      </script>
    </div>
    """
    components.html(html_code, height=height, scrolling=False)

def main():
    st.set_page_config(layout="wide", page_title="OI 异动监控")
    st.title("🚀 主力建仓监控 (OI增幅 > 3%)")

    # 数据缓存处理
    if 'raw_data' not in st.session_state:
        st.session_state.raw_data = load_data(DATA_SOURCE)
    
    df = st.session_state.raw_data
    if df.empty:
        st.error("无法加载数据，请确认后端 API 可用")
        return

    # 筛选
    filtered_df = df[df['increase_ratio'] > 0.03].copy()
    if 'circ_supply' in filtered_df.columns and 'price' in filtered_df.columns:
        filtered_df['market_cap'] = filtered_df['circ_supply'] * filtered_df['price']
    else:
        filtered_df['market_cap'] = 0
    filtered_df = filtered_df.sort_values(by='increase_ratio', ascending=False)

    total_items = len(filtered_df)
    ITEMS_PER_PAGE = 20
    total_pages = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)

    # 刷新按钮
    if st.button("🔄 刷新最新数据"):
        st.session_state.raw_data = load_data(DATA_SOURCE)
        st.rerun()

    st.markdown(f"**当前共有 {total_items} 个活跃合约**")
    st.markdown("---")

    if 'page' not in st.session_state:
        st.session_state.page = 1

    start_idx = (st.session_state.page - 1) * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)
    current_batch = filtered_df.iloc[start_idx:end_idx]

    cols = st.columns(2)
    for i, (_, row) in enumerate(current_batch.iterrows()):
        with cols[i % 2]:
            symbol = row['symbol']
            ratio_pct = row['increase_ratio'] * 100
            inc_val_str = format_money(row['increase_amount_usdt'])
            supply_str = format_money(row.get('circ_supply', 0))
            mcap_str = format_money(row.get('market_cap', 0))

            st.markdown(f"""
            <div style="background-color:#fcfcfc; padding:15px; border-radius:10px; border:1px solid #eee; margin-bottom:10px;">
                <div style="display:flex; justify-content: space-between; align-items: center;">
                    <span style="font-size:1.4em; font-weight:bold;">{symbol}</span>
                    <span style="font-size:1.2em; font-weight:900; color:#d32f2f; background-color:#ffebee; padding:2px 10px; border-radius:4px;">+{ratio_pct:.2f}%</span>
                </div>
                <div style="margin-top:10px; font-size:0.9em; color:#666; display:flex; gap:20px;">
                    <span><b>OI增资:</b> <span style="color:#d32f2f;">+${inc_val_str}</span></span>
                    <span><b>市值:</b> ${mcap_str}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            render_tradingview_widget(symbol)
            st.markdown("<br>", unsafe_allow_html=True)

    # --- 翻页功能 ---
    st.markdown("---")
    _, foot_c2, _ = st.columns([2, 1, 2])
    with foot_c2:
        if total_pages > 1:
            val = st.number_input(f"页码 (共 {total_pages} 页)", 1, total_pages, st.session_state.page)
            if val != st.session_state.page:
                st.session_state.page = val
                st.rerun()

if __name__ == "__main__":
    main()
