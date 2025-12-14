import streamlit as st
import streamlit.components.v1 as components

# --- 核心功能：渲染带 OI 指标的 TradingView ---
def render_tradingview_widget(symbol, height=450):
    """
    渲染嵌入 Open Interest (OI) 指标的 TradingView Widget。
    """
    container_id = f"tv_{symbol}"
    
    # 智能清洗：输入 BTC -> 自动转为 BINANCE:BTCUSDT.P (永续合约)
    clean_symbol = symbol.upper().strip()
    if clean_symbol.endswith("USDT"):
        clean_symbol = clean_symbol[:-4]
    
    tv_symbol = f"BINANCE:{clean_symbol}USDT.P"

    # 注意：为了性能，HTML 部分应保持尽可能精简。
    # 您的原始代码已经很好了，但这里我们移除了部分不必要的 !important 样式。
    html_code = f"""
    <div class="tradingview-widget-container" style="height: {height}px; width: 100%;">
      <div id="{container_id}" style="height: 100%; width: 100%;"></div>
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
            "STD;Fund_crypto_open_interest" // OI 指标 ID
        ],
        // 禁用更多不必要的 UI 元素
        "disabled_features": ["header_symbol_search", "header_compare", "use_localstorage_for_settings", "display_market_status", "timeframes_toolbar"]
      }}
      );
      </script>
    </div>
    """
    # 关键优化点：scrolling=True 允许 Streamlit 内部处理高度，
    # 但由于 TradingView 内部设置了高度，我们还是用 False 保证图表高度固定
    components.html(html_code, height=height, scrolling=False)


# --- 主程序 ---
def main_app():
    st.set_page_config(layout="wide", page_title="Crypto OI Wall")
    st.title("⚡ TradingView OI 监控墙")
    
    # 默认列表 (预设一些热门币)
    default_symbols = [
        "BTC", "ETH", "SOL", "DOGE", 
        "PEPE", "WIF", "ENA", "ORDI", 
        "NEAR", "AVAX", "SUI", "APT",
        "XRP", "LTC", "ADA", "LINK" # 新增一些，便于演示分页效果
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
        # 优化控制：控制每个 Tab 中显示的图表数量，默认为 4 个
        charts_per_tab = st.slider("每个分组（Tab）的图表数量", 2, 6, 4)
    
    # 处理用户输入，转为列表
    symbols = [s.strip().upper() for s in user_input.replace(",", " ").split() if s.strip()]
    
    if not symbols:
        st.warning("请输入至少一个代币代码")
        return

    st.caption(f"当前正在监控 {len(symbols)} 个合约的实时价格与持仓量 (OI)")
    st.markdown("---")

    # --- 关键性能优化：使用 st.tabs 分页加载图表 ---
    
    # 1. 将所有币种分组
    num_tabs = (len(symbols) + charts_per_tab - 1) // charts_per_tab
    symbol_groups = [
        symbols[i:i + charts_per_tab] 
        for i in range(0, len(symbols), charts_per_tab)
    ]
    
    # 2. 创建 Tab 列表
    tab_titles = [f"分组 {i+1} ({len(group)} 个)" for i, group in enumerate(symbol_groups)]
    tabs = st.tabs(tab_titles)

    # 3. 遍历 Tab 组，渲染图表
    for tab_index, group in enumerate(symbol_groups):
        with tabs[tab_index]:
            # 使用两列布局渲染图表
            cols = st.columns(2)
            
            for i, sym in enumerate(group):
                with cols[i % 2]: # 奇数在左，偶数在右
                    # Coinglass 链接
                    coinglass_url = f"https://www.coinglass.com/tv/zh/Binance_{sym}USDT"
                    st.markdown(f"### 🔥 [{sym}]({coinglass_url})")
                    
                    # 渲染图表
                    # 对于 OI 监控，保持高度固定为 450 比较合适
                    render_tradingview_widget(sym, height=450)
                    st.markdown("---")
            
            # 在最后一个 Tab 底部显示总数
            if tab_index == len(symbol_groups) - 1:
                 st.info(f"🎨 所有图表加载完成。总计 {len(symbols)} 个监控对象。")
                

if __name__ == '__main__':
    # 开启 Streamlit 的 set_page_config 之后，即使没有显式调用 main_app() 
    # Streamlit 也会运行整个脚本，所以这里的 __name__ == '__main__' 
    # 依然是标准且必要的。
    main_app()
