import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
from io import StringIO
import os

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

def render_tradingview_widget(symbol, height=400):
    """渲染 TradingView 组件"""
    clean_symbol = symbol.upper().strip()
    tv_symbol = f"BINANCE:{clean_symbol}.P"
    container_id = f"tv_{clean_symbol}"

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
            "STD;Fund_crypto_open_interest"
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

    # 筛选 > 3%
    filtered_df = df[df['increase_ratio'] > 0.03].copy()
    
    # 计算流通市值
    if 'circ_supply' in filtered_df.columns and 'price' in filtered_df.columns:
        filtered_df['market_cap'] = filtered_df['circ_supply'] * filtered_df['price']
    else:
        filtered_df['market_cap'] = 0

    # 排序
    filtered_df = filtered_df.sort_values(by='increase_ratio', ascending=False)

    # 3. 分页逻辑
    total_items = len(filtered_df)
    ITEMS_PER_PAGE = 20
    total_pages = max(1, (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE)

    # --- 顶部控制栏 ---
    c1, c2, c3 = st.columns([1, 2, 3])
    with c1:
        if st.button("🔄 刷新数据", type="primary", use_container_width=True):
            st.rerun()
    with c2:
        if total_pages > 1:
            current_page = st.number_input(
                f"当前页 (共 {total_pages} 页, {total_items} 个标的)", 
                min_value=1, max_value=total_pages, value=1, step=1
            )
        else:
            current_page = 1
            st.markdown(f"**共发现 {total_items} 个标的**")
    
    st.markdown("---")

    # 4. 显示内容
    if filtered_df.empty:
        st.info("😴 当前市场平淡，没有 OI 增幅超过 3% 的合约。")
        return

    # 切片数据
    start_idx = (current_page - 1) * ITEMS_PER_PAGE
    end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)
    current_batch = filtered_df.iloc[start_idx:end_idx]

    # Grid 布局
    cols = st.columns(2)
    
    for i, (_, row) in enumerate(current_batch.iterrows()):
        with cols[i % 2]:
            symbol = row['symbol']
            
            # --- 数据准备 ---
            ratio_pct = row['increase_ratio'] * 100
            inc_val_str = format_money(row['increase_amount_usdt'])
            
            # 流通量
            supply_val = row.get('circ_supply', 0)
            supply_str = format_money(supply_val)
            
            # 流通市值
            mcap_val = row.get('market_cap', 0)
            mcap_str = format_money(mcap_val)

            # --- 标题栏 (调整版：无竖线，大间距) ---
            # 调整说明：
            # 1. 合约名 margin-right 增加到 30px (不那么近)
            # 2. 第二行数据 gap 增加到 35px (稍微远一点)
            # 3. 删除了竖线 |
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
            
            # 渲染图表
            render_tradingview_widget(symbol, height=400)
            st.markdown("<div style='margin-bottom: 20px;'></div>", unsafe_allow_html=True)

if __name__ == "__main__":
    main()
