import streamlit as st
import streamlit.components.v1 as components
import requests
import pandas as pd

# --- 核心功能：渲染带 OI 指标的 TradingView ---
def render_tradingview_widget(symbol, height=400):
    """
    渲染嵌入 Open Interest (OI) 指标的 TradingView Widget。
    高度微调为 400 以节省空间。
    """
    container_id = f"tv_{symbol}"
    
    # 智能清洗：API 返回的是 BTCUSDT，我们需要转换格式
    clean_symbol = symbol.upper().strip()
    if clean_symbol.endswith("USDT"):
        clean_symbol = clean_symbol[:-4]
    
    # 拼接为 BINANCE:BTCUSDT.P
    tv_symbol = f"BINANCE:{clean_symbol}USDT.P"

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
        "hide_top_toolbar": true,       // 隐藏顶部工具栏以节省渲染资源
        "hide_legend": false,
        "save_image": false,
        "container_id": "{container_id}",
        "studies": [
            "MASimple@tv-basicstudies",     
            "STD;Fund_crypto_open_interest" // OI 指标
        ],
        "disabled_features": [
            "header_symbol_search", "header_compare", "use_localstorage_for_settings", 
            "display_market_status", "timeframes_toolbar", "volume_force_overlay",
            "header_chart_type", "header_settings", "header_indicators", "header_screenshot"
        ]
      }}
      );
      </script>
    </div>
    """
    components.html(html_code, height=height, scrolling=False)

# --- 功能：获取币安成交量前 N 名 ---
@st.cache_data(ttl=300) 
def get_top_volume_pairs(limit=100):
    """
    从币安 FAPI 获取 24小时成交量排名的 USDT 永续合约
    """
    url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
    try:
        response = requests.get(url, timeout=10)
        data = response.json()
        
        # 1. 过滤：必须以 USDT 结尾，排除类似 BTCUSD_240628
        usdt_pairs = [
            item for item in data 
            if item['symbol'].endswith('USDT') and '_' not in item['symbol']
        ]
        
        # 2. 排序：按 quoteVolume (USDT成交额) 降序
        sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)
        
        # 3. 截取前 N 名
        top_n = sorted_pairs[:limit]
        
        return [item['symbol'] for item in top_n]
        
    except Exception as e:
        st.error(f"无法连接币安 API: {e}")
        return []

# --- 主程序 ---
def main_app():
    st.set_page_config(layout="wide", page_title="Top 100 Crypto OI Wall")
    st.title("⚡ 币安成交量前 100 强 OI 监控墙")
    
    # --- 侧边栏配置 ---
    with st.sidebar:
        st.header("⚙️ 监控配置")
        
        # 模式选择
        data_source = st.radio("数据来源", ["🏆 币安成交量 Top 100", "📝 手动输入"])
        
        symbols = []
        
        if data_source == "🏆 币安成交量 Top 100":
            if st.button("刷新排名数据", type="primary"):
                st.cache_data.clear()
                st.rerun()
            
            with st.spinner("正在从币安获取实时成交量数据..."):
                symbols = get_top_volume_pairs(100)
            
            if symbols:
                st.success(f"已获取成交量前 {len(symbols)} 名币种")
        
        else:
            default_input = "BTC ETH SOL DOGE PEPE WIF"
            user_input = st.text_area(
                "输入代币代码", 
                value=default_input, 
                height=150
            )
            symbols = [s.strip().upper() for s in user_input.replace(",", " ").split() if s.strip()]

        st.markdown("---")
        st.header("🖥️ 视图控制")
        
        # 分页控制
        total_items = len(symbols)
        if total_items > 0:
            # === 修改点：调整选项并默认选中 50 ===
            items_per_page = st.select_slider(
                "每页显示图表数量",
                options=[10, 20, 50, 100], 
                value=50  # <--- 默认设为 50
            )
            
            total_pages = (total_items + items_per_page - 1) // items_per_page
            
            current_page = st.number_input(
                f"页码 (共 {total_pages} 页)", 
                min_value=1, 
                max_value=total_pages, 
                value=1
            )
            
            start_idx = (current_page - 1) * items_per_page
            end_idx = min(start_idx + items_per_page, total_items)
            
            current_batch = symbols[start_idx:end_idx]
        else:
            current_batch = []
            st.warning("暂无数据")

    # --- 主界面渲染 ---
    if not current_batch:
        return

    st.markdown(f"### 📄 第 {current_page} 页: 排名 {start_idx + 1} - {end_idx}")
    st.markdown("---")

    # 使用 Grid 布局渲染
    cols = st.columns(2)
    
    for i, sym in enumerate(current_batch):
        with cols[i % 2]: 
            clean_sym_for_link = sym.replace("USDT", "") 
            coinglass_url = f"https://www.coinglass.com/tv/zh/Binance_{clean_sym_for_link}USDT"
            
            st.markdown(f"#### #{start_idx + i + 1} [{sym}]({coinglass_url})")
            
            # 渲染图表
            render_tradingview_widget(sym, height=400)
            st.markdown("---")
            
    if end_idx < total_items:
        st.info(f"⬇️ 还有 {total_items - end_idx} 个币种，请在侧边栏翻页。")
    else:
        st.success("🎉 已显示完前 100 名的所有币种。")

if __name__ == '__main__':
    main_app()
