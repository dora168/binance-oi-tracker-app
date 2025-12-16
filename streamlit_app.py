import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import requests
from io import StringIO
import os

# ================= 核心配置区 =================

# 🔴 这里必须修改！填入你的 CSV 地址
# 如果你用了 Cpolar，这里填 Cpolar 给你的公网地址，例如：
# DATA_SOURCE = "http://2808xxxx.cpolar.cn/oi_analysis.csv"

# 如果你在局域网，填服务器的内网 IP，例如：
# DATA_SOURCE = "http://192.168.1.100:8080/oi_analysis.csv"

# 默认占位符（你需要改掉它）
DATA_SOURCE = "http://43.156.132.4:8080/oi_analysis.csv" 

# ============================================

def render_tradingview_widget(symbol, height=400):
    """渲染嵌入 Open Interest (OI) 指标的 TradingView Widget"""
    # 清洗数据，确保格式为纯币种名称 (例如 BTC)
    clean_symbol = symbol.upper().strip()
    if clean_symbol.endswith("USDT"):
        clean_symbol = clean_symbol[:-4]
    
    # 构造 TradingView 能够识别的代码
    tv_symbol = f"BINANCE:{clean_symbol}USDT.P"
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

def load_data(source):
    """加载远程或本地 CSV 数据"""
    try:
        # 如果是 HTTP 链接
        if source.startswith("http"):
            response = requests.get(source, timeout=10)
            if response.status_code != 200:
                st.error(f"❌ 无法连接到数据源 (状态码: {response.status_code})")
                return pd.DataFrame()
            
            # 尝试用 utf-8-sig 解码 (兼容中文)
            try:
                content = response.content.decode('utf-8-sig')
            except:
                content = response.content.decode('gbk') # 备用 GBK 解码
            
            df = pd.read_csv(StringIO(content))
        
        # 如果是本地文件路径 (备用)
        else:
            if not os.path.exists(source):
                st.error(f"❌ 文件不存在: {source}")
                return pd.DataFrame()
            df = pd.read_csv(source)
            
        return df
    except Exception as e:
        st.error(f"❌ 数据加载出错: {e}")
        return pd.DataFrame()

# --- 主程序逻辑 ---
def main():
    st.set_page_config(layout="wide", page_title="OI 异常监控墙")
    st.title("🚀 主力建仓监控 (基于3日Min-Max)")

    # 1. 刷新按钮
    if st.button("🔄 刷新数据"):
        st.cache_data.clear()
        st.rerun()

    # 2. 加载数据
    with st.spinner(f"正在从 {DATA_SOURCE} 获取数据..."):
        df = load_data(DATA_SOURCE)
    
    if df.empty:
        st.warning("暂无数据。请检查服务器端的 Python HTTP 服务是否开启，以及 Cpolar 地址是否正确。")
        st.stop()

    # 3. 侧边栏筛选
    with st.sidebar:
        st.header("🔍 筛选条件")
        
        # 增加比例滑块
        min_ratio = st.slider("最小增加比例 (%)", 0.0, 10.0, 0.5, step=0.1)
        
        # 将小数转为百分比用于筛选 (假设CSV里 increase_ratio 是小数)
        # 兼容处理：先复制一份
        df_display = df.copy()
        if 'increase_ratio' in df_display.columns:
            df_display['ratio_pct'] = df_display['increase_ratio'] * 100
        else:
            st.error("CSV 中缺少 'increase_ratio' 列")
            st.stop()
            
        filtered_df = df_display[df_display['ratio_pct'] >= min_ratio]
        
        st.write(f"监控总数: {len(df)}")
        st.write(f"符合条件: {len(filtered_df)}")
        st.markdown("---")
        
        # 分页设置
        items_per_page = st.select_slider("每页显示图表数", options=[10, 20, 50], value=20)
        total_items = len(filtered_df)
        total_pages = max(1, (total_items + items_per_page - 1) // items_per_page)
        current_page = st.number_input(f"页码 (共 {total_pages} 页)", 1, total_pages, 1)

    # 4. 显示数据表格 (Top 榜单)
    st.subheader("📊 异动排行榜")
    if not filtered_df.empty:
        # 格式化显示的列
        table_df = filtered_df.copy()
        table_df['increase_amount_usdt'] = table_df['increase_amount_usdt'].apply(lambda x: f"${format_money(x)}")
        table_df['ratio_pct'] = table_df['ratio_pct'].apply(lambda x: f"{x:.2f}%")
        table_df['price'] = table_df['price'].apply(lambda x: f"${float(x):.4f}")
        
        # 只显示关键列
        cols_to_show = ['symbol', 'ratio_pct', 'increase_amount_usdt', 'price']
        # 确保这些列都存在
        cols_to_show = [c for c in cols_to_show if c in table_df.columns]
        
        st.dataframe(
            table_df[cols_to_show],
            use_container_width=True,
            hide_index=True
        )
    else:
        st.info("当前没有符合筛选条件的币种。")

    st.markdown("---")

    # 5. K线墙展示 (分页)
    if not filtered_df.empty:
        start_idx = (current_page - 1) * items_per_page
        end_idx = min(start_idx + items_per_page, total_items)
        current_batch = filtered_df.iloc[start_idx:end_idx]

        st.subheader(f"📈 重点监控图表 ({start_idx+1} - {end_idx})")
        
        cols = st.columns(2) # 两列布局
        for i, (_, row) in enumerate(current_batch.iterrows()):
            with cols[i % 2]:
                symbol = row['symbol']
                ratio = row['ratio_pct']
                money = format_money(row['increase_amount_usdt'])
                
                # 标题栏
                st.markdown(f"""
                <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:5px;">
                    <h3 style="margin:0;">{symbol}</h3>
                    <div style="text-align:right;">
                        <span style="color:#4CAF50; font-weight:bold; font-size:1.2em;">+{ratio:.2f}%</span><br>
                        <span style="color:gray; font-size:0.9em;">💰 +${money}</span>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                render_tradingview_widget(symbol)
                st.markdown("---")

if __name__ == "__main__":
    main()
