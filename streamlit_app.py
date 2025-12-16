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
    """将数字格式化为 B/M/K (用户指定格式)"""
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
        # 设置超时时间，防止卡死
        response = requests.get(url, timeout=5)
        
        if response.status_code != 200:
            st.error(f"❌ 无法连接服务器，状态码: {response.status_code}")
            return pd.DataFrame()
        
        # 处理编码，防止中文乱码 (优先 utf-8-sig, 备用 gbk)
        try:
            content = response.content.decode('utf-8-sig')
        except:
            content = response.content.decode('gbk')
            
        df = pd.read_csv(StringIO(content))
        return df
    except Exception as e:
        st.error(f"❌ 数据加载失败: {e}")
        st.caption("请检查：1.服务器上的 python -m http.server 是否开启。 2.防火墙 8080 端口是否放行。")
        return pd.DataFrame()

def render_tradingview_widget(symbol, height=400):
    """渲染 TradingView 组件"""
    # 假设 CSV 里的 symbol 是 BTCUSDT，TradingView 需要 BINANCE:BTCUSDT.P
    clean_symbol = symbol.upper().strip()
    
    # 构造 TradingView 格式
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

    # 1. 顶部操作栏
    col1, col2 = st.columns([1, 6])
    with col1:
        if st.button("🔄 刷新数据", type="primary"):
            st.rerun()
    with col2:
        st.caption(f"数据源: {DATA_SOURCE}")

    # 2. 加载数据
    with st.spinner("正在从服务器获取最新数据..."):
        df = load_data(DATA_SOURCE)
    
    if df.empty:
        return

    # 3. 数据处理与筛选
    # 确保有 increase_ratio 列
    if 'increase_ratio' not in df.columns:
        st.error("CSV 文件中缺少 'increase_ratio' 列，请检查后端脚本。")
        st.dataframe(df.head())
        return

    # === 核心逻辑修改：只获取增加比例大于 3% 的合约 ===
    # 假设 increase_ratio 是小数 (0.03 代表 3%)
    filtered_df = df[df['increase_ratio'] > 0.03]

    # 按比例从高到低排序
    filtered_df = filtered_df.sort_values(by='increase_ratio', ascending=False)

    # 4. 显示结果 & 分页逻辑
    if filtered_df.empty:
        st.info("😴 当前市场平淡，没有 OI 增幅超过 3% 的合约。")
    else:
        total_items = len(filtered_df)
        ITEMS_PER_PAGE = 20
        
        # 计算总页数
        total_pages = (total_items + ITEMS_PER_PAGE - 1) // ITEMS_PER_PAGE
        
        # === 侧边栏：分页控制 ===
        with st.sidebar:
            st.header("📄 分页控制")
            st.write(f"共发现: **{total_items}** 个标的")
            
            if total_pages > 1:
                current_page = st.number_input(
                    f"页码 (共 {total_pages} 页)", 
                    min_value=1, 
                    max_value=total_pages, 
                    value=1,
                    step=1
                )
            else:
                current_page = 1
                st.caption("数量较少，无需分页")
        
        # === 数据切片 ===
        start_idx = (current_page - 1) * ITEMS_PER_PAGE
        end_idx = min(start_idx + ITEMS_PER_PAGE, total_items)
        
        current_batch = filtered_df.iloc[start_idx:end_idx]
        
        st.success(f"🔥 发现 {total_items} 个猛烈建仓合约 (当前显示第 {start_idx + 1} - {end_idx} 名)")
        
        # 使用 Grid 布局展示图表 (两列)
        cols = st.columns(2)
        
        for i, (_, row) in enumerate(current_batch.iterrows()):
            with cols[i % 2]:
                symbol = row['symbol']
                # 计算百分比显示
                ratio_pct = row['increase_ratio'] * 100
                # 使用你指定的 format_money 函数格式化金额
                amount_str = format_money(row['increase_amount_usdt'])
                # 价格 (转为float再显示，防止报错)
                try:
                    price_val = float(row['price'])
                    price_str = f"{price_val}"
                except:
                    price_str = str(row['price'])

                # 标题栏信息
                st.markdown(f"""
                <div style="background-color:#f0f2f6; padding:10px; border-radius:5px; margin-bottom:5px;">
                    <div style="display:flex; justify-content:space-between; align-items:center;">
                        <h3 style="margin:0; color:#333;">{symbol}</h3>
                        <div style="text-align:right;">
                            <span style="font-size:1.2em; font-weight:bold; color:#d32f2f;">+{ratio_pct:.2f}%</span><br>
                            <span style="font-size:0.9em; color:#666;">💰 +${amount_str}</span>
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # 渲染图表
                render_tradingview_widget(symbol, height=400)
                st.markdown("---")

if __name__ == "__main__":
    main()
