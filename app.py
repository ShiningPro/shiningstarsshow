import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="ShiningStar v75 BREAKOUT", layout="wide")
st.title("ShiningStar v75 - RSI BREAKOUT Audited")

STOCKS = ["BBCA.JK","BBRI.JK","BMRI.JK","TLKM.JK","ASII.JK","UNVR.JK","ICBP.JK","TRUK.JK","CBRE.JK","RMKO.JK","BREN.JK","CUAN.JK","BBYB.JK","GOTO.JK","BUKA.JK","PTRO.JK","INET.JK","WIFI.JK","BIPI.JK","BRMS.JK"]
THRESHOLD = 75
TARGET = 0.04
STOP = -0.02
FEE_BUY = 0.0015
FEE_SELL = 0.0025

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.where(delta>0, 0).rolling(period).mean()
    loss = -delta.where(delta<0, 0).rolling(period).mean()
    rs = gain / (loss + 1e-9)
    return 100 - (100 / (1 + rs))

def calculate_score(df):
    try:
        if df is None or len(df) < 25: return 0
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        if 'Close' not in df.columns or 'Volume' not in df.columns: return 0
        close = df['Close']
        vol = df['Volume']
        if close.isna().all(): return 0
        sma20 = close.rolling(20).mean()
        sma5 = close.rolling(5).mean()
        vol_avg = vol.rolling(20).mean()
        high20 = close.rolling(20).max()
        r = rsi(close, 14)
        if pd.isna(sma20.iloc[-1]) or pd.isna(vol_avg.iloc[-1]) or pd.isna(r.iloc[-1]): return 0

        # FILTER DEAD <5B
        if len(df) >=5:
            val5 = float((close.iloc[-5:] * vol.iloc[-5:]).sum())
            if val5 < 5_000_000_000: return 0

        score = 50
        # NEW BREAKOUT LOGIC
        # 1. Near 20-day high (0-2% below) = breakout setup +15
        if close.iloc[-1] >= high20.iloc[-1] * 0.98:
            score += 15
        # 2. Strong volume 1.5x = institutional buying +10
        if vol.iloc[-1] >= vol_avg.iloc[-1] * 1.5:
            score += 10
        # 3. RSI healthy 55-70 = momentum but not overbought +10
        if 55 <= r.iloc[-1] <= 70:
            score += 10
        # 4. RSI overbought >75 = penalize -15 (don't buy top)
        if r.iloc[-1] > 75:
            score -= 15
        # 5. Trend filter +5+5
        if sma5.iloc[-1] > sma20.iloc[-1]:
            score += 5
        if close.iloc[-1] > sma20.iloc[-1]:
            score += 5
        # 6. Distribution trap
        if close.pct_change(5).iloc[-1] < 0 and vol.iloc[-1] > vol_avg.iloc[-1]*3:
            return 45

        return min(100, max(0, int(score)))
    except:
        return 0

@st.cache_data(ttl=3600)
def get_data(ticker, period):
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=False)
        if df.empty: return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except:
        return pd.DataFrame()

def backtest_stock(ticker):
    df = get_data(ticker, "6mo")
    if df.empty or len(df) < 40: return None
    split = int(len(df)*0.66)
    def run_period(start_idx, end_idx):
        trades=[]; equity_curve=[1.0]; peak=1.0; max_dd=0; in_until=-1
        for i in range(start_idx, end_idx-1):
            if i <= in_until or i < 20: continue
            score = calculate_score(df.iloc[:i+1])
            if score >= THRESHOLD:
                if i+1 >= len(df): continue
                entry = float(df['Open'].iloc[i+1])
                entry_date = df.index[i+1]
                open_e = float(df['Open'].iloc[i+1]); high_e = float(df['High'].iloc[i+1]); low_e = float(df['Low'].iloc[i+1])
                if open_e <= entry*(1+STOP):
                    exit_price = open_e; in_until = i+1; result = "LOSS (gap open below stop)"
                else:
                    ht_e = high_e >= entry*(1+TARGET); hs_e = low_e <= entry*(1+STOP)
                    if ht_e and hs_e: exit_price = entry*(1+STOP); in_until = i+1; result = "LOSS (both hit entry day)"
                    elif hs_e: exit_price = entry*(1+STOP); in_until = i+1; result = "LOSS (stop entry day)"
                    elif ht_e: exit_price = entry*(1+TARGET); in_until = i+1; result = "WIN (target entry day)"
                    else:
                        exit_price = None
                        for j in range(i+2, min(i+12, len(df))):
                            if float(df['Open'].iloc[j]) <= entry*(1+STOP):
                                exit_price = float(df['Open'].iloc[j]); in_until=j; result=f"LOSS (gap open day {j-i})"; break
                            ht = float(df['High'].iloc[j]) >= entry*(1+TARGET); hs = float(df['Low'].iloc[j]) <= entry*(1+STOP)
                            if ht and hs: exit_price=entry*(1+STOP); in_until=j; result="LOSS (both hit)"; break
                            elif hs: exit_price=entry*(1+STOP); in_until=j; result="LOSS"; break
                            elif ht: exit_price=entry*(1+TARGET); in_until=j; result="WIN"; break
                        if exit_price is None:
                            exit_price=float(df['Close'].iloc[min(i+11,len(df)-1)]); in_until=min(i+11,len(df)-1); result="TIME_EXIT D+10"
                buy_cost=entry*(1+FEE_BUY); sell=exit_price*(1-FEE_SELL); pnl_pct=(sell-buy_cost)/buy_cost*100
                equity_curve.append(equity_curve[-1]*(1+pnl_pct/100)); peak=max(peak, equity_curve[-1]); dd=(peak-equity_curve[-1])/peak*100; max_dd=max(max_dd, dd)
                trades.append({"EntryDate":entry_date.date(),"Score":score,"Entry":round(entry,1),"Exit":round(exit_price,1),"Result":result,"PnL%":round(pnl_pct,2),"Win":pnl_pct>0})
        if not trades: return {"trades":0,"winrate":0,"net_compounded":0,"max_dd":0,"details":[],"equity":1.0}
        df_t=pd.DataFrame(trades); net_comp = (equity_curve[-1]-1)*100
        return {"trades":len(trades),"winrate":round(df_t["Win"].mean()*100,1),"net_compounded":round(net_comp,2),"max_dd":round(max_dd,2),"details":trades,"equity":equity_curve[-1]}
    full = run_period(20, len(df)); train = run_period(20, split); test = run_period(split, len(df))
    if not full: return None
    return {"ticker":ticker,"full":full,"train":train,"test":test}

tab1, tab2 = st.tabs(["LIVE TODAY","BACKTEST v75 BREAKOUT"])
with tab1:
    rows=[]
    for t in STOCKS:
        df = get_data(t, "3mo"); sc = calculate_score(df)
        rows.append({"Stock":t,"Score":sc,"Signal":"BUY" if sc>=THRESHOLD else "WAIT"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
with tab2:
    st.write("v75 FIXES: Breakout 20H + Vol 1.5x + RSI 55-70, Overbought penalty >75")
    results=[]
    for t in STOCKS:
        with st.spinner(f"Backtesting {t}"):
            r=backtest_stock(t)
            if r: results.append(r)
    summary=[]
    for r in results:
        summary.append({"Stock":r["ticker"],"Trades Full":r["full"]["trades"],"WR% Full":r["full"]["winrate"],"Net% Compounded Full":r["full"]["net_compounded"],"MaxDD%":r["full"]["max_dd"],"Trades Train 4mo":r["train"]["trades"],"WR Train":r["train"]["winrate"],"Trades Test 2mo":r["test"]["trades"],"WR Test (unseen)":r["test"]["winrate"],"Net% Test":r["test"]["net_compounded"]})
    st.dataframe(pd.DataFrame(summary), use_container_width=True)
    st.warning("If Trades Test <5, not reliable. WR Test <50% = threshold not valid.")
    sel=st.selectbox("Detail", STOCKS)
    for r in results:
        if r["ticker"]==sel:
            st.write(f"FULL {r['ticker']}"); st.dataframe(pd.DataFrame(r["full"]["details"]).tail(20), use_container_width=True)
            st.write(f"UNSEEN TEST 2mo"); st.dataframe(pd.DataFrame(r["test"]["details"]), use_container_width=True)
