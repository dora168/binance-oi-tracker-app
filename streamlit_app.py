import streamlit as st
import pandas as pd
import altair as alt
import os
import connectorx as cx
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor
import streamlit.components.v1 as components

# --- A. 数据库配置 ----

DB_HOST = os.getenv("DB_HOST") or st.secrets.get("DB_HOST", "cd-cdb-p6vea42o.sql.tencentcdb.com")
DB_PORT = int(os.getenv("DB_PORT") or st.secrets.get("DB_PORT", 24197))
DB_USER = os.getenv("DB_USER") or st.secrets.get("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD") or st.secrets.get("DB_PASSWORD", None)

DB_NAME_OI = 'open_interest_db'
DB_NAME_SUPPLY = 'circulating_supply'

DATA_LIMIT_RAW = 4000
SAMPLE_STEP = 10 

# --- B. 数据库功能 (Rust加速 + 修复URL) ---

@st.cache_resource
def get_db_uri(db_name):
    """构建 connectorx 需要的连接字符串"""
    if not DB_PASSWORD:
        st.error("❌ 数据库密码未配置。")
        st.stop()
    
    safe_pwd = quote_plus(DB_PASSWORD)
    # ⚠️ 关键修复：不包含 charset 参数
    return f"mysql://{DB_USER}:{safe_pwd}@{DB_HOST}:{DB_PORT}/{db_name}"

def _fetch_supply_worker():
    """线程任务1：获取流通量"""
    try:
        uri = get_db_uri(DB_NAME_SUPPLY)
        query = f"SELECT symbol, circulating_supply, market_cap FROM `binance_circulating_supply`"
        df = cx.read_sql(uri, query)
        return df.set_index('symbol').to_dict('index')
    except Exception as e:
        print(f"⚠️ 流通量读取失败: {e}")
        return {}

def _fetch_market_data_worker(limit=150):
    """线程任务2：获取K线数据"""
    uri = get_db_uri(DB_NAME_OI)
    
    # 1. 先拿列表
    try:
        list_query = "SELECT symbol FROM `binance` GROUP BY symbol ORDER BY MAX(oi_usd) DESC LIMIT 200"
        df_list = cx.read_sql(uri, list_query)
        sorted_symbols = df_list['symbol'].tolist()
    except Exception as e:
        return {}, []

    if not sorted_symbols: return {}, []
    
    target_symbols = sorted_symbols[:limit]
    symbols_str = "', '".join(target_symbols)
    
    # 2. 再拿详情 (SQL降采样优化)
    sql_query = f"""
    WITH RankedData AS (
        SELECT symbol, `time`, `price`, `oi`,
        ROW_NUMBER() OVER (PARTITION BY symbol ORDER BY `time` DESC) as rn
        FROM `binance`
        WHERE symbol IN ('{symbols_str}')
    )
    SELECT symbol, `time`, `price` AS `标记价格 (USDC)`, `oi` AS `未平仓量`
    FROM RankedData
    WHERE rn <= {DATA_LIMIT_RAW} 
    AND (rn = 1 OR rn % {SAMPLE_STEP} = 0)
    ORDER BY symbol, `time` ASC;
    """
    
    try:
        df_all = cx.read_sql(uri, sql_query)
        if df_all.empty: return {}, target_symbols
        
        if not pd.api.types.is_datetime64_any_dtype(df_all['time']):
            df_all['time'] = pd.to_datetime(df_all['time'])
            
        df_all['标记价格 (USDC)'] = df_all['标记价格 (USDC)'].astype(float)
        df_all['未平仓量'] = df_all['未平仓量'].astype(float)

        return {sym: group for sym, group in df_all.groupby('symbol')}, target_symbols
    except Exception as e:
        print(f"⚠️ 市场数据读取失败: {e}")
        return {}, target_symbols

@st.cache_data(ttl=60, show_spinner=False)
def fetch_all_data_concurrently():
    """并发入口"""
    with ThreadPoolExecutor(max_workers=2) as executor:
        future_supply = executor.submit(_fetch_supply_worker)
        future_market = executor.submit(_fetch_market_data_worker, 150)
        
        supply_data = future_supply.result()
        bulk_data, target_symbols = future_market.result()
        
    return supply_data, bulk_data, target_symbols

# --- C. 辅助与绘图 ---

def format_number(num):
    if abs(num) >= 1_000_000_000: return f"{num / 1_000_000_000:.2f}B"
    elif abs(num) >= 1_000_000: return f"{num / 1_000_000:.2f}M"
    elif abs(num) >= 1_000: return f"{num / 1_000:.1f}K"
    else: return f"{num:.0f}"

def downsample_data(df, target_points=200):
    if len(df) <= target_points * 1.5: return df
    step = len(df) // target_points
    return df.iloc[::step]

axis_format_logic = """
datum.value >= 1000000000 ? format(datum.value / 1000000000, ',.2f') + 'B' : 
datum.value >= 1000000 ? format(datum.value / 1000000, ',.2f') + 'M' : 
datum.value >= 1000 ? format(datum.value / 1000, ',.1f') + 'K' : 
format(datum.value, ',.0f')
"""

def create_dual_axis_chart(df, symbol):
    if df.empty: return None
    base = alt.Chart(df).encode(alt.X('time', axis=alt.Axis(labels=False, title=None)))
    line_price = base.mark_line(color='#d62728', strokeWidth=2).encode(
        alt.Y('标记价格 (USDC)', axis=alt.Axis(title='', titleColor='#d62728', orient='right'), scale=alt.Scale(zero=False))
    )
    line_oi = base.mark_line(color='purple', strokeWidth=2).encode(
        alt.Y('未平仓量', axis=alt.Axis(title='OI', titleColor='purple', orient='right', offset=45, labelExpr=axis_format_logic), scale=alt.Scale(zero=False))
    )
    return alt.layer(line_price, line_oi).resolve_scale(y='independent').properties(height=350)

# --- TradingView Widget (加载 Crypto Open Interest) ---
def render_tradingview_widget(symbol, height=380):
    container_id = f"tv_{symbol}"
    
    clean_symbol = symbol.upper().replace("USDT", "")
    tv_symbol = f"BINANCE:{clean_symbol}USDT.P"

    html_code = f"""
    <style>
        body, html {{ 
            margin: 0 !important; 
            padding: 0 !important; 
            height: 100% !important; 
            width: 100% !important; 
            overflow: hidden !important;
            background-color: #ffffff;
        }}
        .tradingview-widget-container {{ 
            height: 100% !important; 
            width: 100% !important; 
        }}
        #{container_id} {{
            height: 100% !important; 
            width: 100% !important; 
        }}
    </style>

    <div class="tradingview-widget-container">
      <div id="{container_id}"></div>
      <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
      <script type="text/javascript">
      new TradingView.widget(
      {{
        "autosize": true,
        "symbol": "{tv_symbol}",
        "interval": "15",
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
            "MASimple@tv-basicstudies",     // 均线
            "OpenInterest@tv-basicstudies"  // 这是标准Open Interest的内部ID，通常也对应"Crypto Open Interest"
        ],
        "disabled_features": [
            "header_symbol_search", 
            "header_compare", 
            "use_localstorage_for_settings", 
            "display_market_status"
        ]
      }}
      );
      </script>
    </div>
    """
    components.html(html_code, height=height, scrolling=False)

def render_chart_component(rank, symbol, bulk_data, ranking_data, is_top_mover=False, list_type="", use_tv=False):
    raw_df = bulk_data.get(symbol)
    coinglass_url = f"https://www.coinglass.com/tv/zh/Binance_{symbol}USDT"
    
    title_color = "black"
    chart = None
    info_html = ""
    
    if raw_df is not None and not raw_df.empty:
        p_vals = raw_df['标记价格 (USDC)'].values
        start_p, end_p = p_vals[0], p_vals[-1]
        title_color = "#009900" if end_p >= start_p else "#D10000"
        
        item_stats = next((item for item in ranking_data if item["symbol"] == symbol), None)
        if item_stats:
            int_val = item_stats['intensity'] * 100
            int_color = "#d62728" if int_val > 5 else ("#009900" if int_val > 1 else "#555")
            growth_usd = item_stats['oi_growth_usd']
            growth_str = format_number(growth_usd)
            
            info_html = (
                f'<span style="font-size: 14px; margin-left: 10px; color: #666;">'
                f'强度:<span style="color: {int_color}; font-weight: bold;">{int_val:.1f}%</span>'
                f'<span style="margin: 0 4px;">|</span>'
                f'增量:<span style="color: #009900; font-weight: bold;">+${growth_str}</span>'
                f'</span>'
            )
        
        if not use_tv:
            chart_df = downsample_data(raw_df, target_points=400)
            chart = create_dual_axis_chart(chart_df, symbol)

    fire_icon = "🔥" if list_type == "strength" else ("🐳" if list_type == "whale" else "")
    expander_title_html = (
        f'<div style="text-align: center; margin-bottom: 5px;">'
        f'{fire_icon} '
        f'<a href="{coinglass_url}" target="_blank" '
        f'style="text-decoration:none; color:{title_color}; font-weight:bold; font-size:20px;">'
        f' {symbol} </a>'
        f'{info_html}'
        f'</div>'
    )
    
    label = f"{fire_icon} {symbol}" if is_top_mover else f"#{rank} {symbol}"

    with st.expander(label, expanded=True):
        st.markdown(expander_title_html, unsafe_allow_html=True)
        if use_tv:
            render_tradingview_widget(symbol, height=380)
        elif chart:
            st.altair_chart(chart, use_container_width=True)
        else:
            st.info("暂无数据")

# --- D. 主程序 ---

def main_app():
    st.set_page_config(layout="wide", page_title="Binance OI Dashboard")
    st.title("⚡ Binance OI 双塔监控 (TradingView + OI指标)")
    
    with st.spinner("🚀 极速加载中 (Rust引擎 + 多线程并发)..."):
        supply_data, bulk_data, target_symbols = fetch_all_data_concurrently()

    if not bulk_data:
        st.warning("暂无数据"); st.stop()

    ranking_data = []
    for sym, df in bulk_data.items():
        if df.empty or len(df) < 2: continue
        
        token_info = supply_data.get(sym)
        current_price = df['标记价格 (USDC)'].iloc[-1]
        
        min_oi = df['未平仓量'].min()
        current_oi = df['未平仓量'].iloc[-1]
        oi_growth_usd = (current_oi - min_oi) * current_price
        
        market_cap = 0
        supply = 0
        db_market_cap = 0
        
        if token_info:
            try: supply = float(token_info.get('circulating_supply') or 0)
            except: pass
            try: db_market_cap = float(token_info.get('market_cap') or 0)
            except: pass

        intensity = 0
        if supply > 0:
            market_cap = supply * current_price
            intensity = oi_growth_usd / market_cap
        elif db_market_cap > 0:
            market_cap = db_market_cap
            intensity = oi_growth_usd / market_cap
        else:
            oi_growth_tokens = current_oi - min_oi
            if min_oi > 0: intensity = (oi_growth_tokens / min_oi) * 0.1

        ranking_data.append({
            "symbol": sym,
            "intensity": intensity, 
            "oi_growth_usd": oi_growth_usd,
            "market_cap": market_cap
        })

    col_left, col_right = st.columns(2)
    
    ranking_data.sort(key=lambda x: x['intensity'], reverse=True)
    top_intensity = ranking_data[:10]
    
    ranking_data.sort(key=lambda x: x['oi_growth_usd'], reverse=True)
    top_whales = ranking_data[:10]

    with col_left:
        st.subheader("🔥 Top 10 强度榜")
        st.markdown("---")
        for i, item in enumerate(top_intensity):
            st.metric(f"No.{i+1} {item['symbol']}", f"{item['intensity']*100:.2f}%", f"MC: ${format_number(item['market_cap'])}", delta_color="off")
            st.markdown("""<hr style="margin: 2px 0;">""", unsafe_allow_html=True)
            
    with col_right:
        st.subheader("🐳 Top 10 巨鲸榜")
        st.markdown("---")
        for i, item in enumerate(top_whales):
            st.metric(f"No.{i+1} {item['symbol']}", f"+${format_number(item['oi_growth_usd'])}", "资金净流入")
            st.markdown("""<hr style="margin: 2px 0;">""", unsafe_allow_html=True)
    
    st.markdown("---")
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("📈 强度 Top 10 (Live)")
        for i, item in enumerate(top_intensity, 1):
            render_chart_component(i, item['symbol'], bulk_data, ranking_data, True, "strength", use_tv=True)
            
    with c2:
        st.subheader("📈 巨鲸 Top 10 (Live)")
        for i, item in enumerate(top_whales, 1):
            render_chart_component(i, item['symbol'], bulk_data, ranking_data, True, "whale", use_tv=True)

    st.markdown("---")
    st.subheader("📋 其他合约列表")

    shown = {i['symbol'] for i in top_intensity} | {i['symbol'] for i in top_whales}
    remaining = [s for s in target_symbols if s not in shown]

    for rank, symbol in enumerate(remaining, 1):
        render_chart_component(rank, symbol, bulk_data, ranking_data, is_top_mover=False, use_tv=False)

if __name__ == '__main__':
    main_app()
