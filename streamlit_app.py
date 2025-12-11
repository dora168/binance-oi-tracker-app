import streamlit as st
import streamlit.components.v1 as components

# --- 核心功能：渲染带 OI 指标的 TradingView ---
def render_tradingview_widget(symbol, height=450):
    container_id = f"tv_{symbol}"
    
    # 智能清洗：输入 BTC -> 自动转为 BINANCE:BTCUSDT.P
    clean_symbol = symbol.upper().strip()
    if clean_symbol.endswith("USDT"):
        clean_symbol = clean_symbol[:-4]
    
    tv_symbol = f"BINANCE:{clean_symbol}USDT.P"

    html_code = f"""
    <style>
        body, html {{ margin: 0 !important; padding: 0 !important; height: 100% !important; width: 100% !important; overflow: hidden !important; background-color: #ffffff; }}
        .tradingview-widget-container {{ height: 100% !important; width: 100% !important; }}
        #{container_id} {{ height: 100% !important; width: 100% !important; }}
    </style>
    <div class="tradingview-widget-container">
      <div id="{container_id}"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
        "autosize": true,
        "symbol": "{tv_symbol}",
        "interval": "60",          // 默认显示1小时图
        "timezone": "Asia/Shanghai",
        "theme": "light",
        "style": "1",
        "locale": "zh_CN",
        "enable_publishing": false,
        "hide_top_toolbar": false,
        "hide_legend": false,
        "save_image": false,
        "container_id": "{container_id}",
        "studies": [
            "MASimple@tv-basicstudies",    
            "STD;Fund_crypto_open_interest" // 🎯 你找到的那个正确 OI 指标 ID
        ],
        "disabled_features": ["header_symbol_search", "header_compare", "use_localstorage_for_settings", "display_market_status"]
      }}
      );
      </script>
    </div>
    """
    components.html(html_code, height=height, scrolling=False)

# --- 主程序 ---
def main_app():
    st.set_page_config(layout="wide", page_title="Crypto OI Wall")
    st.title("⚡ TradingView OI 监控墙")
    
    # 默认列表 (既然没有数据库了，我们预设一些热门币)
    default_symbols = [
        "BTC", "ETH", "SOL", "DOGE", 
        "PEPE", "WIF", "ENA", "ORDI", 
        "NEAR", "AVAX", "SUI", "APT"
    ]
    
    # 侧边栏：允许你随时修改要监控的币种
    with st.sidebar:
        st.header("⚙️ 监控配置")
        user_input = st.text_area(
            "输入代币代码 (空格或逗号分隔)", 
            value=" ".join(default_symbols), 
            height=300,
            help="输入例如: BTC ETH SOL，系统会自动拼接成 USDT 永续合约地址"
        )
    
    # 处理用户输入，转为列表
    symbols = [s.strip().upper() for s in user_input.replace(",", " ").split() if s.strip()]
    
    if not symbols:
        st.warning("请输入至少一个代币代码")
        return

    st.caption(f"当前正在监控 {len(symbols)} 个合约的实时价格与持仓量 (OI)")
    st.markdown("---")

    # 使用两列布局渲染图表
    cols = st.columns(2)
    
    for i, sym in enumerate(symbols):
        with cols[i % 2]: # 奇数在左，偶数在右
            # 这里的链接方便你点进去看详情
            coinglass_url = f"https://www.coinglass.com/tv/zh/Binance_{sym}USDT"
            st.markdown(f"### 🔥 [{sym}]({coinglass_url})")
            
            # 渲染图表
            render_tradingview_widget(sym, height=450)
            st.markdown("---")

if __name__ == '__main__':
    main_app()
