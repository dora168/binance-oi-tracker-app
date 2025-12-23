import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
from io import StringIO

# ================= 核心配置区 =================
# 1. 设置数据源
DATA_SOURCE = "http://43.156.132.4:8080/oi_analysis.csv"
# 2. 每页显示数量 (不使用折叠时，建议设为 10 以防浏览器崩溃)
ITEMS_PER_PAGE = 10 
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

# --- 添加数据缓存，有效期 60 秒 ---
@st.cache_data(ttl=600)
def load_data(url):
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return pd.DataFrame()
        # 自动尝试多种编码防止乱码
        try:
            content = response.content.decode('utf-8-sig')
        except:
            content = response.content.decode('gbk')
        return pd.read_csv(StringIO(content))
    except Exception as e:
        return pd.DataFrame()

def render_tradingview_widget(symbol, height=450):
    clean_symbol = symbol.upper().strip()
    tv_symbol = f"BINANCE:{clean_symbol}.P"
    container_id = f"tv_{clean_symbol}"
    html_code = f"""
    <div class="tradingview-widget-container" style="height: {height}px; width: 100%;">
      <div id="{container_id}" style="height: 100%; width: 100%;"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget({{
        "autosize": true, "symbol": "{tv_symbol}", "interval": "60",
        "timezone": "Asia/Shanghai", "theme": "light", "style": "1",
        "locale": "zh_CN", "enable_publishing": false, "hide_top_toolbar": true,
        "container_id": "{container_id}",
        "studies": ["MASimple@tv-basicstudies", "STD;Fund_crypto_open_interest"],
        "disabled_features": [
            "header_symbol_search", "header_compare", "use_localstorage_for_settings", 
            "display_market_status", "timeframes_toolbar", "volume_force_overlay"
        ]
      }});
      </script>
    </div>
    """
    components.html(html_code, height=height, scrolling=False)

def main():
    st.set_page_config(layout="wide", page_title="OI 异动监控")
    st.title("🚀 主力建仓监控 (OI增幅 > 3%)")

    # 1. 加载数据 (使用缓存)
    with st.spinner("正在同步全市场数据..."):
        df = load_data(DATA_SOURCE)
    
    if df.empty:
        st.warning("数据加载中或暂无异动标的，请稍后刷新。")
        return

    # 2. 数据处理
    filtered_df = df[df['increase_ratio'] > 0.03].copy()
    if 'circ_supply' in filtered_df.columns and 'price' in filtered_df.columns:
        filtered_df['market_cap'] = filtered_df['circ_supply'] * filtered_df['price']
    else:
        filtered_df['market_cap'] = 0
    filtered_df = filtered_df.sort_values(by='increase_ratio', ascending=False)

    # 3. 分页设置
    total_items = len(filtered_df)
    total_pages = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)
    if 'page' not in st.session_state:
        st.session_state.page = 1

    # --- 顶部统计 ---
    st.info(f"📊 监控运行中 | 发现 {total_items} 个标的 | 缓存每 60 秒刷新")
    
    start_idx = (st.session_state.page - 1) * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)
    current_batch = filtered_df.iloc[start_idx:end_idx]

    # 4. 平铺显示数据卡片与图表
    cols = st.columns(2)
    for i, (_, row) in enumerate(current_batch.iterrows()):
        with cols[i % 2]:
            symbol = row['symbol']
            ratio_pct = row['increase_ratio'] * 100
            inc_val = format_money(row['increase_amount_usdt'])
            mcap = format_money(row.get('market_cap', 0))

            # 精简后的卡片布局
            st.markdown(f"""
            <div style="background-color:#ffffff; padding:15px; border-radius:10px; border:2px solid #f0f2f6; margin-bottom:10px;">
                <div style="display:flex; justify-content: space-between; align-items: center;">
                    <span style="font-size:1.5em; font-weight:bold;">{symbol}</span>
                    <span style="font-size:1.2em; font-weight:bold; color:#d32f2f; background-color:#ffebee; padding:4px 12px; border-radius:6px;">
                        +{ratio_pct:.2f}%
                    </span>
                </div>
                <div style="margin-top:10px; color:#666; font-size:1em;">
                    <b>OI 增资:</b> <span style="color:#d32f2f;">${inc_val}</span> | 
                    <b>市值:</b> <span style="color:#1976d2;">${mcap}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            # 图表直接平铺显示
            render_tradingview_widget(symbol, height=450)
            st.markdown("<br>", unsafe_allow_html=True)

    # --- 底部翻页 ---
    st.markdown("---")
    _, footer_col, _ = st.columns([2, 1, 2])
    with footer_col:
        if total_pages > 1:
            new_page = st.number_input(f"页码 (共 {total_pages} 页)", 1, total_pages, value=st.session_state.page)
            if new_page != st.session_state.page:
                st.session_state.page = new_page
                st.rerun()

if __name__ == "__main__":
    main()
