import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
from io import StringIO

# ================= 核心配置区 =================

# 1. 设置数据源 (固定 IP)
DATA_SOURCE = "http://43.156.132.4:8080/oi_analysis.csv"

# ============================================

def format_money(num):
    """将数字格式化为 B/M/K"""
    try:
        num = float(num)
        if num >= 1_000_000_000: return f"{num/1_000_000_000:.2f}B"
        if num >= 1_000_000: return f"{num/1_000_000:.2f}M"
        if num >= 1_000: return f"{num/1_000:.0f}K"
        return f"{num:.0f}"
    except:
        return str(num)

def load_data(url):
    """从远程 URL 加载 CSV 数据"""
    try:
        response = requests.get(url, timeout=5)
        if response.status_code != 200:
            st.error(f"❌ 无法连接服务器，状态码: {response.status_code}")
            return pd.DataFrame()
        
        try:
            content = response.content.decode('utf-8-sig')
        except:
            content = response.content.decode('gbk')
            
        df = pd.read_csv(StringIO(content))
        return df
    except Exception as e:
        st.error(f"❌ 数据加载失败: {e}")
        return pd.DataFrame()

def render_tradingview_widget(symbol, height=450):
    """渲染 TradingView 组件"""
    clean_symbol = symbol.upper().strip()
    tv_symbol = f"BINANCE:{clean_symbol}.P"
    container_id = f"tv_{clean_symbol}"

    # 在 studies 列表中增加了多空比指标
    html_code = f"""
    <div class="tradingview-widget-container" style="height: {height}px; width: 100%;">
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
            "Internal$STD;Fund_long_short_ratio"
        ],
        "disabled_features": [
            "header_symbol_search", "header_compare", "use_localstorage_for_settings", 
            "display_market_status", "timeframes_toolbar", "volume_force_overlay",
            "header_chart_type", "header_settings", "header_indicators"
        ]
      }}
      );
      </script>
    </div>
    """
    components.html(html_code, height=height, scrolling=False)

def main():
    st.set_page_config(layout="wide", page_title="OI 异动监控")
    st.title("🚀 主力建仓监控 (OI增幅 > 3%)")

    # 1. 加载数据
    with st.spinner("正在获取最新数据..."):
        df = load_data(DATA_SOURCE)
    
    if df.empty:
        return

    # 2. 数据清洗与筛选
    if 'increase_ratio' not in df.columns:
        st.error("数据缺失 'increase_ratio' 列")
        return

    filtered_df = df[df['increase_ratio'] > 0.03].copy()
    
    if 'circ_supply' in filtered_df.columns and 'price' in filtered_df.columns:
        filtered_df['market_cap'] = filtered_df['circ_supply'] * filtered_df['price']
    else:
        filtered_df['market_cap'] = 0

    filtered_df = filtered_df.sort_values(by='increase_ratio', ascending=False)

    # 3. 分页逻辑准备
    total_items = len(filtered_df)
    ITEMS_PER_PAGE = 20
    total_pages = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)

    # --- 顶部控制栏 (仅保留刷新和统计) ---
    c1, c2 = st.columns([1, 5])
    with c1:
        if st.button("🔄 刷新数据", type="primary", use_container_width=True):
            st.rerun()
    with c2:
        st.markdown(f"<div style='padding-top:7px;'><b>共发现 {total_items} 个标的，分为 {total_pages} 页显示</b></div>", unsafe_allow_html=True)
    
    st.markdown("---")

    # 获取当前页码 (使用 Session State 确保翻页流畅)
    if 'page' not in st.session_state:
        st.session_state.page = 1

    # 4. 显示内容
    if filtered_df.empty:
        st.info("😴 当前市场平淡，没有 OI 增幅超过 3% 的合约。")
        return

    # 切片数据
    start_idx = (st.session_state.page - 1) * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)
    current_batch = filtered_df.iloc[start_idx:end_idx]

    # Grid 布局
    cols = st.columns(2)
    
    for i, (_, row) in enumerate(current_batch.iterrows()):
        with cols[i % 2]:
            symbol = row['symbol']
            ratio_pct = row['increase_ratio'] * 100
            inc_val_str = format_money(row['increase_amount_usdt'])
            supply_str = format_money(row.get('circ_supply', 0))
            mcap_str = format_money(row.get('market_cap', 0))

            st.markdown(f"""
            <div style="background-color:#f8f9fa; padding:12px; border-radius:8px; border:1px solid #e0e0e0; margin-bottom:10px;">
                <div style="display:flex; align-items:center; margin-bottom: 8px;">
                    <span style="font-size:1.3em; font-weight:bold; color:#000; margin-right: 30px;">{symbol}</span>
                    <span style="font-size:1.2em; font-weight:900; color:#d32f2f; background-color:#ffebee; padding:2px 10px; border-radius:4px;">+{ratio_pct:.2f}%</span>
                </div>
                <div style="display:flex; flex-wrap:wrap; align-items:center; font-size:0.95em; color:#424242; gap: 35px;">
                    <span><b>OI增资:</b> <span style="color:#d32f2f;">+${inc_val_str}</span></span>
                    <span><b>流通量:</b> {supply_str}</span>
                    <span><b>市值:</b> <span style="color:#1976d2;">${mcap_str}</span></span>
                </div>
            </div>
            """, unsafe_allow_html=True)
            
            render_tradingview_widget(symbol, height=450) # 略微增加高度以容纳新指标
            st.markdown("<div style='margin-bottom: 30px;'></div>", unsafe_allow_html=True)

    # --- 底部控制栏 (翻页装置) ---
    st.markdown("---")
    footer_c1, footer_c2, footer_c3 = st.columns([2, 1, 2])
    with footer_c2:
        if total_pages > 1:
            new_page = st.number_input(
                f"跳至页码 (1-{total_pages})", 
                min_value=1, max_value=total_pages, 
                value=st.session_state.page, 
                key="page_input"
            )
            if new_page != st.session_state.page:
                st.session_state.page = new_page
                st.rerun()
        else:
            st.markdown("<p style='text-align:center;'>已显示全部数据</p>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
