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
        return f"{num:.1f}"
    except:
        return str(num)

def load_data(url):
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200: return pd.DataFrame()
        content = response.content.decode('utf-8-sig')
        return pd.read_csv(StringIO(content))
    except:
        return pd.DataFrame()

def render_tradingview_widget(symbol, height=600):
    """
    通过 overrides 强制规范指标显示位置，减少 Calculation failed 带来的排版混乱
    """
    clean_symbol = symbol.upper().strip()
    tv_symbol = f"BINANCE:{clean_symbol}.P"
    container_id = f"tv_{clean_symbol}"

    html_code = f"""
    <div class="tradingview-widget-container" style="height: {height}px; width: 100%; background: #fff;">
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
            "header_symbol_search", "header_compare", "timeframes_toolbar", "volume_force_overlay"
        ],
        "overrides": {{
            "paneProperties.topMargin": 10,
            "paneProperties.bottomMargin": 5,
            "mainSeriesProperties.style": 1
        }}
      }}
      );
      </script>
    </div>
    """
    components.html(html_code, height=height, scrolling=False)

def main():
    st.set_page_config(layout="wide", page_title="OI 异动监控")
    
    # 侧边栏设置
    with st.sidebar:
        st.header("⚙️ 设置")
        items_per_page = st.select_slider("每页显示数量", options=[4, 6, 10, 20], value=10)
        st.info("💡 如果指标显示报错，请尝试降低每页数量或点击下方按钮刷新。")
        if st.button("🔄 重新加载全量数据", use_container_width=True):
            st.session_state.clear()
            st.rerun()

    st.title("🚀 主力建仓监控 (OI增幅 > 3%)")

    # 1. 数据获取
    if 'data' not in st.session_state:
        df = load_data(DATA_SOURCE)
        if not df.empty:
            df = df[df['increase_ratio'] > 0.03].copy()
            if 'circ_supply' in df.columns and 'price' in df.columns:
                df['market_cap'] = df['circ_supply'] * df['price']
            df = df.sort_values(by='increase_ratio', ascending=False)
            st.session_state.data = df
        else:
            st.session_state.data = pd.DataFrame()

    df = st.session_state.data
    if df.empty:
        st.warning("暂无符合条件的数据。")
        return

    # 2. 分页处理
    total_items = len(df)
    total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
    
    if 'page' not in st.session_state:
        st.session_state.page = 1

    start_idx = (st.session_state.page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, total_items)
    current_batch = df.iloc[start_idx:end_idx]

    # 3. 页面渲染
    st.write(f"📊 发现 **{total_items}** 个高增幅合约 (当前显示 {start_idx+1}-{end_idx})")
    
    cols = st.columns(2)
    for i, (_, row) in enumerate(current_batch.iterrows()):
        with cols[i % 2]:
            # 头部信息卡片
            st.markdown(f"""
            <div style="background-color:#ffffff; padding:15px; border-radius:10px 10px 0 0; border:1px solid #ddd; border-bottom:none;">
                <div style="display:flex; justify-content: space-between; align-items: center;">
                    <span style="font-size:1.5em; font-weight:bold; color:#1e1e1e;">{row['symbol']}</span>
                    <span style="font-size:1.2em; font-weight:bold; color:#d32f2f; background-color:#ffebee; padding:4px 12px; border-radius:6px;">+{row['increase_ratio']*100:.2f}%</span>
                </div>
                <div style="margin-top:10px; display:flex; gap:25px; font-size:0.95em;">
                    <span>💵 <b>OI增资:</b> <span style="color:#d32f2f;">${format_money(row['increase_amount_usdt'])}</span></span>
                    <span>🌍 <b>市值:</b> ${format_money(row.get('market_cap', 0))}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # 图表区
            render_tradingview_widget(row['symbol'])
            st.markdown("<div style='margin-bottom: 35px;'></div>", unsafe_allow_html=True)

    # 4. 底部翻页（增强型）
    st.markdown("---")
    c1, c2, c3 = st.columns([2, 1, 2])
    with c2:
        if total_pages > 1:
            new_page = st.number_input(f"页码 (共 {total_pages} 页)", 1, total_pages, st.session_state.page)
            if new_page != st.session_state.page:
                st.session_state.page = new_page
                st.rerun()

if __name__ == "__main__":
    main()
