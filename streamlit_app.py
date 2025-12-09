import streamlit as st
import pandas as pd
import altair as alt
import os
import connectorx as cx
from urllib.parse import quote_plus
from concurrent.futures import ThreadPoolExecutor, as_completed

# --- A. 数据库配置 ----

DB_HOST = os.getenv("DB_HOST") or st.secrets.get("DB_HOST", "cd-cdb-p6vea42o.sql.tencentcdb.com")
DB_PORT = int(os.getenv("DB_PORT") or st.secrets.get("DB_PORT", 24197))
DB_USER = os.getenv("DB_USER") or st.secrets.get("DB_USER", "root")
DB_PASSWORD = os.getenv("DB_PASSWORD") or st.secrets.get("DB_PASSWORD", None)

DB_NAME_OI = 'open_interest_db'
DB_NAME_SUPPLY = 'circulating_supply'

DATA_LIMIT_RAW = 4000
SAMPLE_STEP = 5 

# --- B. 数据库功能 (并发 + Rust) ---

@st.cache_resource
def get_db_uri(db_name):
    if not DB_PASSWORD:
        st.error("❌ 数据库密码未配置。")
        st.stop()
    safe_pwd = quote_plus(DB_PASSWORD)
    return f"mysql://{DB_USER}:{safe_pwd}@{DB_HOST}:{DB_PORT}/{db_name}"

# 拆分函数以便并行调用，移除装饰器缓存（让主函数控制并发缓存）
def _fetch_supply_worker():
    try:
        uri = get_db_uri(DB_NAME_SUPPLY)
        query = f"SELECT symbol, circulating_supply, market_cap FROM `binance_circulating_supply`"
        df = cx.read_sql(uri, query)
        return df.set_index('symbol').to_dict('index')
    except Exception as e:
        print(f"⚠️ 流通量读取失败: {e}")
        return {}

def _fetch_market_data_worker(limit=150):
    """
    这是一个组合任务：先拿列表，再拿K线数据，在一个线程内完成
    """
    uri = get_db_uri(DB_NAME_OI)
    
    # 1. 获取列表
    try:
        # 限制只取前 limit 个，减少后续计算量
        list_query = "SELECT symbol FROM `binance` GROUP BY symbol ORDER BY MAX(oi_usd) DESC LIMIT 200"
        df_list = cx.read_sql(uri, list_query)
        sorted_symbols = df_list['symbol'].tolist()
    except Exception as e:
        return {}, []

    if not sorted_symbols: return {}, []
    
    target_symbols = sorted_symbols[:limit]
    symbols_str = "', '".join(target_symbols)
    
    # 2. 获取K线 (SQL降采样)
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
        
        bulk_data = {sym: group for sym, group in df_all.groupby('symbol')}
        return bulk_data, target_symbols
    except Exception as e:
        print(f"⚠️ 市场数据读取失败: {e}")
        return {}, target_symbols

@st.cache_data(ttl=60, show_spinner=False)
def fetch_all_data_concurrently():
    """
    🔥 并发核心：同时发射两个火箭
    """
    with ThreadPoolExecutor(max_workers=2) as executor:
        # 提交两个任务
        future_supply = executor.submit(_fetch_supply_worker)
        future_market = executor.submit(_fetch_market_data_worker, 150) # 限制前150
        
        # 等待结果
        supply_data = future_supply.result()
        bulk_data, target_symbols = future_market.result()
        
    return supply_data, bulk_data, target_symbols

# --- C. 辅助与绘图 (保持极致精简) ---

def format_number(num):
    if abs(num) >= 1_000_000_000: return f"{num / 1_000_000_000:.2f}B"
    elif abs(num) >= 1_000_000: return f"{num / 1_000_000:.2f}M"
    elif abs(num) >= 1_000: return f"{num / 1_000:.1f}K"
    else: return f"{num:.0f}"

def downsample_data(df, target_points=400):
    if len(df) <= target_points * 1.5: return df
    step = len(df) // target_points
    return df.iloc[::step]

axis_format_logic = """
datum.value >= 1000000000 ? format(datum.value / 1000000000, ',.2f') + 'B' : 
datum.value >= 1000000 ? format(datum.value / 1000000, ',.2f') + 'M' : 
datum.value >= 1000 ? format(datum.value / 1000, ',.1f') + 'K' : 
format(datum.value, ',.0f')
"""

def create_dual_axis_chart(df):
    # 移除 symbol 参数，减少传参
    if df.empty: return None
    # 极速绘图：只保留核心逻辑
    base = alt.Chart(df).encode(alt.X('time', axis=alt.Axis(labels=False, title=None))) # 直接用时间，不用Index，更快
    
    line_price = base.mark_line(color='#d62728', strokeWidth=2).encode(
        alt.Y('标记价格 (USDC)', axis=alt.Axis(title='', titleColor='#d62728', orient='right'), scale=alt.Scale(zero=False))
    )
    line_oi = base.mark_line(color='purple', strokeWidth=2).encode(
        alt.Y('未平仓量', axis=alt.Axis(title='OI', titleColor='purple', orient='right', offset=45, labelExpr=axis_format_logic), scale=alt.Scale(zero=False))
    )
    
    return alt.layer(line_price, line_oi).resolve_scale(y='independent').properties(height=350) 

def render_chart_component(rank, symbol, bulk_data, ranking_data, is_top_mover=False, list_type=""):
    raw_df = bulk_data.get(symbol)
    coinglass_url = f"https://www.coinglass.com/tv/zh/Binance_{symbol}USDT"
    
    title_color = "black"
    chart = None
    info_html = ""
    
    if raw_df is not None and not raw_df.empty:
        # 简单快速的价格比较
        p_vals = raw_df['标记价格 (USDC)'].values
        start_p, end_p = p_vals[0], p_vals[-1]
        title_color = "#009900" if end_p >= start_p else "#D10000"
        
        item_stats = next((item for item in ranking_data if item["symbol"] == symbol), None)
        if item_stats:
            int_val = item_stats['intensity'] * 100
            int_color = "#d62728" if int_val > 5 else ("#009900" if int_val > 1 else "#555")
            growth_usd = item_stats['oi_growth_usd']
            
            info_html = (
                f'<span style="font-size: 13px; margin-left: 8px; color: #666;">'
                f'强度:<span style="color: {int_color}; font-weight: bold;">{int_val:.1f}%</span>'
                f' | 增量:<span style="color: #009900; font-weight: bold;">+${format_number(growth_usd)}</span>'
                f'</span>'
            )

        # 进一步减少绘图点数，提升浏览器渲染速度
        chart_df = downsample_data(raw_df, target_points=200) 
        chart = create_dual_axis_chart(chart_df)

    fire_icon = "🔥" if list_type == "strength" else ("🐳" if list_type == "whale" else "")
    
    # 优化 HTML 结构
    expander_title_html = (
        f'<div style="text-align: center;">'
        f'{fire_icon} <a href="{coinglass_url}" target="_blank" style="text-decoration:none; color:{title_color}; font-weight:bold; font-size:18px;">{symbol}</a>'
        f'{info_html}'
        f'</div>'
    )
    
    label = f"{fire_icon} {symbol}" if is_top_mover else f"#{rank} {symbol}"

    with st.expander(label, expanded=True):
        st.markdown(expander_title_html, unsafe_allow_html=True)
        if chart:
            st.altair_chart(chart, use_container_width=True)
        else:
            st.text("No Data")

# --- D. 主程序 ---

def main_app():
    st.set_page_config(layout="wide", page_title="Binance OI Ultra Fast")
    st.title("⚡ Binance OI 极速监控")
    
    # 🚀 并发加载：不再分步等待，一次性拿回所有数据
    with st.spinner("🚀 双线程并发加载数据中..."):
        supply_data, bulk_data, target_symbols = fetch_all_data_concurrently()

    if not bulk_data:
        st.warning("暂无数据"); st.stop()

    # --- 极速计算逻辑 ---
    ranking_data = []
    
    # 预处理：将 supply data 转换为更快的查找结构 (dict lookup is O(1))
    # 已经在 fetch 中转为 dict，直接使用
    
    for sym, df in bulk_data.items():
        if df.empty or len(df) < 2: continue
        
        # 使用 numpy values 加速读取，比 iloc 快
        prices = df['标记价格 (USDC)'].values
        ois = df['未平仓量'].values
        
        current_price = prices[-1]
        min_oi = ois.min()
        current_oi = ois[-1]
        
        oi_growth_usd = (current_oi - min_oi) * current_price
        
        token_info = supply_data.get(sym, {})
        
        # 简化的市值获取逻辑
        market_cap = 0
        try:
            if token_info.get('circulating_supply'):
                market_cap = float(token_info['circulating_supply']) * current_price
            elif token_info.get('market_cap'):
                market_cap = float(token_info['market_cap'])
        except: pass

        # 强度计算
        intensity = 0
        if market_cap > 0:
            intensity = oi_growth_usd / market_cap
        elif min_oi > 0:
            intensity = ((current_oi - min_oi) / min_oi) * 0.1

        ranking_data.append({
            "symbol": sym,
            "intensity": intensity, 
            "oi_growth_usd": oi_growth_usd,
            "market_cap": market_cap
        })

    # --- 渲染逻辑 ---
    col_left, col_right = st.columns(2)
    
    # 排序
    ranking_data.sort(key=lambda x: x['intensity'], reverse=True)
    top_intensity = ranking_data[:10]
    
    ranking_data.sort(key=lambda x: x['oi_growth_usd'], reverse=True)
    top_whales = ranking_data[:10]

    # 指标显示优化：使用容器减少重排
    with col_left:
        st.subheader("🔥 Top 10 强度")
        st.markdown("---")
        for i, item in enumerate(top_intensity):
            st.metric(f"No.{i+1} {item['symbol']}", f"{item['intensity']*100:.2f}%", f"MC: ${format_number(item['market_cap'])}", delta_color="off")
            st.markdown("""<hr style="margin: 2px 0;">""", unsafe_allow_html=True) # 更紧凑
            
    with col_right:
        st.subheader("🐳 Top 10 巨鲸")
        st.markdown("---")
        for i, item in enumerate(top_whales):
            st.metric(f"No.{i+1} {item['symbol']}", f"+${format_number(item['oi_growth_usd'])}", "资金净流入")
            st.markdown("""<hr style="margin: 2px 0;">""", unsafe_allow_html=True)
    
    st.markdown("---")
    
    # 图表区
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("Top 10 强度走势")
        for i, item in enumerate(top_intensity, 1):
            render_chart_component(i, item['symbol'], bulk_data, ranking_data, True, "strength")
            
    with c2:
        st.subheader("Top 10 巨鲸走势")
        for i, item in enumerate(top_whales, 1):
            render_chart_component(i, item['symbol'], bulk_data, ranking_data, True, "whale")

    st.markdown("---")
    st.caption(f"已监控合约数: {len(target_symbols)} | 数据点优化: ON | Rust引擎: ON")

    # 底部列表：为了极致性能，这里建议只渲染Top 20以外的前20个，或者做分页
    # 如果必须渲染全部100+个，浏览器会卡。这里做一个简单的折叠。
    
    shown = {i['symbol'] for i in top_intensity} | {i['symbol'] for i in top_whales}
    remaining = [s for s in target_symbols if s not in shown]
    
    if remaining:
        with st.expander(f"📋 查看其余 {len(remaining)} 个合约 (点击展开)", expanded=False):
            # 使用网格布局快速显示其余的，不画图，只显示数据，这是提升前端速度的关键
            # 如果非要画图，取消下面的注释，但会卡顿
            st.write("为保证页面流畅，剩余合约仅显示简报：")
            
            # 转换为DataFrame快速展示
            rem_data = []
            for sym in remaining:
                stats = next((r for r in ranking_data if r['symbol'] == sym), None)
                if stats:
                    rem_data.append({
                        "Token": sym,
                        "强度": f"{stats['intensity']*100:.2f}%",
                        "流入($)": f"{format_number(stats['oi_growth_usd'])}",
                        "市值": format_number(stats['market_cap'])
                    })
            st.dataframe(pd.DataFrame(rem_data), use_container_width=True)

            # 如果一定要画图，请取消下面代码的注释，但浏览器可能会卡死
            for i, sym in enumerate(remaining, 1):
                render_chart_component(i+20, sym, bulk_data, ranking_data)

if __name__ == '__main__':
    main_app()
