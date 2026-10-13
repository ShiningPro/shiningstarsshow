import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="ShiningStar v72 FINAL", layout="wide")
st.title("ShiningStar v72 - FINAL Audited")

STOCKS = ["BBCA.JK","BBRI.JK","BMRI.JK","TLKM.JK","ASII.JK","UNVR.JK","ICBP.JK"]
THRESHOLD = 61
TARGET = 0.015
STOP = -0.007
FEE_BUY = 0.0015
FEE_SELL = 0.0025

def calculate_score(df):
    if len(df) < 20: return 0
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    close = df['Close']
    sma20 = close.rolling(20).mean()
    sma5 = close.rolling(5).mean()
    vol_avg = df['Volume'].rolling(20).mean()
    score = 50
    if close.iloc[-1] > sma20.iloc[-1]: score += 10
    if sma5.iloc[-1] > sma20.iloc[-1]: score += 10
    if df['Volume'].iloc[-1] > vol_avg.iloc[-1]: score += 5
    if close.pct_change(5).iloc[-1] > 0: score += 8
    if close.iloc[-1] > close.rolling(20).min().iloc[-1] * 1.02: score += 5
    return min(100, max(0, int(score)))

def backtest_stock(ticker):
    df = yf.download(ticker, period="6mo", interval="1d", progress=False)
    if df.empty or len(df) < 30: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    trades = []
    equity_curve = [1.0]
    peak = 1.0
    max_dd = 0
    in_until = -1
    for i in range(20, len(df)-2):
        if i <= in_until: continue
        score = calculate_score(df.iloc[:i+1])
        if score >= THRESHOLD:
            entry = float(df['Open'].iloc[i+1])
            entry_date = df.index[i+1]
            exit_price = None
            for j in range(i+2, min(i+12, len(df))):
                ht = float(df['High'].iloc[j]) >= entry*(1+TARGET)
                hs = float(df['Low'].iloc[j]) <= entry*(1+STOP)
                if ht and hs:
                    exit_price = entry*(1+STOP); in_until=j; result="LOSS (both hit->STOP)"; break
                elif hs:
                    exit_price = entry*(1+STOP); in_until=j; result="LOSS"; break
                elif ht:
                    exit_price = entry*(1+TARGET); in_until=j; result="WIN"; break
            if exit_price is None:
                exit_price = float(df['Close'].iloc[min(i+11, len(df)-1)])
                in_until = min(i+11, len(df)-1)
                result = "TIME_EXIT D+10"
            buy_cost = entry*(1+FEE_BUY); sell = exit_price*(1-FEE_SELL)
            pnl_pct = (sell-buy_cost)/buy_cost*100
            equity_curve.append(equity_curve[-1]*(1+pnl_pct/100))
            peak = max(peak, equity_curve[-1])
            dd = (peak-equity_curve[-1])/peak*100
            max_dd = max(max_dd, dd)
            trades.append({"EntryDate":entry_date.date(),"Score":score,"Entry@NextOpen":round(entry,1),"Exit":round(exit_price,1),"Result":result,"PnL%_afterFees":round(pnl_pct,2),"Win":pnl_pct>0})
    if not trades:
        return {"ticker":ticker,"trades":0,"winrate":0,"net":0,"max_dd":0,"details":[]}
    df_t = pd.DataFrame(trades)
    return {"ticker":ticker,"trades":len(trades),"winrate":round(df_t["Win"].mean()*100,1),"net":round(df_t["PnL%_afterFees"].sum(),2),"max_dd":round(max_dd,2),"details":trades}

tab1, tab2 = st.tabs(["LIVE TODAY","BACKTEST v72 FINAL"])
with tab1:
    rows=[]
    for t in STOCKS:
        df=yf.download(t, period="3mo", interval="1d", progress=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns=df.columns.get_level_values(0)
        sc=calculate_score(df)
        rows.append({"Stock":t,"Score":sc,"Signal":"BUY" if sc>=THRESHOLD else "WAIT"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
with tab2:
    st.caption("FIXED: Entry=Next Open, Exit=Day+10, Fees in Win, No Overlap, Real Net%")
    results=[]
    for t in STOCKS:
        r=backtest_stock(t)
        if r: results.append(r)
    summary=pd.DataFrame([{"Stock":r["ticker"],"Trades":r["trades"],"WinRate%_afterFees":r["winrate"],"Net%_sum":r["net"],"MaxDD%":r["max_dd"]} for r in results])
    st.dataframe(summary, use_container_width=True)
    sel=st.selectbox("Detail", STOCKS)
    for r in results:
        if r["ticker"]==sel:
            st.dataframe(pd.DataFrame(r["details"]).tail(30), use_container_width=True)
