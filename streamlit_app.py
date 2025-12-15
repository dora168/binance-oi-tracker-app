import streamlit as st
import streamlit.components.v1 as components
import requests

# --- 核心配置 ---
# 如果 API 失败，使用这份静态的 Top 50 热门币种列表作为保底
FALLBACK_SYMBOLS = [
    "BTC", "ETH", "SOL", "BNB", "DOGE", "XRP", "ADA", "AVAX", "SHIB", "DOT",
    "LINK", "TRX", "MATIC", "NEAR", "LTC", "BCH", "UNI", "APT", "FIL", "IMX",
    "ARB", "OP", "INJ", "RNDR", "ATOM", "ETC", "XLM", "STX", "SUI", "VET",
    "ORDI", "WIF", "PEPE", "THETA", "FTM", "ALGO", "TIA", "SEI", "GRT", "AAVE",
    "FLOW", "SAND", "MANA", "EGLD", "AXS", "XTZ", "EOS", "QNT", "GALA", "NEO"
]

# --- 组件：渲染 TradingView Widget ---
def render_tradingview_widget(symbol, height=400):
    """
    渲染嵌入 Open Interest (OI) 指标的 TradingView Widget
    """
    # 清洗数据，确保格式为纯币种名称 (例如 BTC)
    clean_symbol = symbol.upper().strip()
    if clean_symbol.endswith("USDT"):
        clean_symbol = clean_symbol[:-4]
    
    # 构造 TradingView 能够识别的 币安永续合约 代码
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

# --- 数据获取：带容错机制 ---
@st.cache_data(ttl=600) # 缓存10分钟
def get_market_data(limit=100):
    """
    尝试从 API 获取数据，如果失败（被墙），则返回保底列表。
    """
    # 尝试 1: CoinGecko API (比币安更容易在云端访问)
    try:
        url = "https://api.coingecko.com/api/v3/coins/markets"
        params = {
            "vs_currency": "usd",
            "order": "volume_desc", # 按成交量排序
            "per_page": limit,
            "page": 1,
            "sparkline": "false"
        }
        response = requests.get(url, params=params, timeout=3)
        if response.status_code == 200:
            data = response.json()
            # 提取 symbol 并转大写
            return [item['symbol'].upper() for item in data], "API (CoinGecko)"
    except:
        pass

    # 尝试 2: 币安 API (在本地有效，但云端常被封锁)
    try:
        url = "https://fapi.binance.com/fapi/v1/ticker/24hr"
        response = requests.get(url, timeout=3)
        if response.status_code == 200:
            data = response.json()
            usdt_pairs = [x for x in data if x['symbol'].endswith('USDT') and '_' not in x['symbol']]
            sorted_pairs = sorted(usdt_pairs, key=lambda x: float(x['quoteVolume']), reverse=True)
            # 这里的 symbol 已经是 BTCUSDT 格式
            return [x['symbol'] for x in sorted_pairs[:limit]], "API (Binance)"
    except:
        pass

    # 如果都失败，返回保底列表
    return FALLBACK_SYMBOLS, "离线保底列表 (API 连接受限)"

# --- 主程序逻辑 ---
def main():
    st.set_page_config(layout="wide", page_title="Crypto OI Wall")
    
    st.title("⚡ 币安成交量 Top 100 - OI 监控墙")

    # 1. 获取数据
    with st.spinner("正在加载市场数据..."):
        symbols, source_type = get_market_data(100)

    # 2. 侧边栏控制
    with st.sidebar:
        st.header("⚙️ 控制面板")
        
        # 显示数据源状态
        if "离线" in source_type:
            st.warning(f"⚠️ 当前使用：{source_type}")
            st.caption("原因：云服务器 IP 可能被交易所暂时拦截，已自动切换至预设热门币种，不影响图表查看。")
        else:
            st.success(f"✅ 数据来源：{source_type}")

        if st.button("强制刷新数据"):
            st.cache_data.clear()
            st.rerun()
            
        st.markdown("---")
        
        # 分页设置
        total_items = len(symbols)
        items_per_page = st.select_slider("每页显示数量", options=[10, 20, 50, 100], value=50)
        
        # 计算页数
        total_pages = (total_items + items_per_page - 1) // items_per_page
        current_page = st.number_input(f"页码 (共 {total_pages} 页)", min_value=1, max_value=total_pages, value=1)

    # 3. 数据切片
    start_idx = (current_page - 1) * items_per_page
    end_idx = min(start_idx + items_per_page, total_items)
    current_batch = symbols[start_idx:end_idx]

    # 4. 页面显示
    st.markdown(f"**当前显示：第 {start_idx + 1} - {end_idx} 名**")
    
    # 渲染图表 Grid
    cols = st.columns(2) # 两列布局
    for i, sym in enumerate(current_batch):
        with cols[i % 2]:
            # 生成跳转链接
            link_symbol = sym.replace("USDT", "")
            url = f"https://www.coinglass.com/tv/zh/Binance_{link_symbol}USDT"
            
            st.markdown(f"#### #{start_idx + i + 1} {sym} ([Coinglass]({url}))")
            render_tradingview_widget(sym)
            st.markdown("---")

    if end_idx >= total_items:
        st.success("已显示全部加载的币种。")

if __name__ == "__main__":
    main()
