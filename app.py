import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="ShiningStar v76.2 LIGHT", layout="wide")
st.title("ShiningStar v76.2 - LIGHT FIXED")

STOCKS = ["BBCA.JK","BBRI.JK","BMRI.JK","TLKM.JK","ASII.JK","UNVR.JK","ICBP.JK","TRUK.JK","CBRE.JK","RMKO.JK"]
THRESHOLD = 70 # Lower to 70 for MANDATORY to get some trades
TARGET = 0.04
STOP = -0.02
FEE_BUY = 0.0015
FEE_SELL = 0.0025

def rsi(series, p=14):
    d = series.diff()
    g = d.where(d>0,0).rolling(p).mean()
    l = -d.where(d<0,0).rolling(p).mean()
    rs = g/(l+1e-9)
    return 100 - (100/(1+rs))

def calculate_score(df):
    if df is None or len(df) < 25: return 0
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    close = df['Close']; high = df['High']; vol = df['Volume']
    sma20 = close.rolling(20).mean()
    sma5 = close.rolling(5).mean()
    vol_avg = vol.rolling(20).mean()
    high20_prev = high.rolling(20).max().shift(1) # TRUE BREAKOUT FIX
    r = rsi(close)
    if pd.isna(sma20.iloc[-1]) or pd.isna(high20_prev.iloc[-1]) or pd.isna(r.iloc[-1]): return 0
    # dead filter
    if len(df)>=5:
        if float((close.iloc[-5:]*vol.iloc[-5:]).sum()) < 5_000_000_000: return 0
    # MANDATORY: must be near true high
    if close.iloc[-1] < high20_prev.iloc[-1]*0.98: return 0
    if sma5.iloc[-1] <= sma20.iloc[-1]: return 0
    score = 70
    if vol.iloc[-1] >= vol_avg.iloc[-1]*1.5: score+=10
    if 55 <= r.iloc[-1] <= 70: score+=10
    if r.iloc[-1] > 78: score-=20
    return min(100,max(0,int(score)))

@st.cache_data(ttl=3600)
def get_data(ticker, period="1y"):
    try:
        df = yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=False)
        if df.empty: return pd.DataFrame()
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        return df.dropna()
    except: return pd.DataFrame()

def backtest_stock(ticker):
    df = get_data(ticker, "1y")
    if df.empty or len(df)<60: return None
    split = int(len(df)*0.7)
    def run_period(s,e):
        trades=[]; eq=[1.0]; peak=1.0; mdd=0; in_until=-1
        for i in range(s, e-1):
            if i<=in_until or i<25: continue
            sc = calculate_score(df.iloc[:i+1])
            if sc>=THRESHOLD:
                if i+1>=e: continue
                entry = float(df['Open'].iloc[i+1])
                exit_price=None; result=""
                max_hold = min(i+11, e-1)
                for j in range(i+1, max_hold+1):
                    if j>=len(df): break
                    o=float(df['Open'].iloc[j]); h=float(df['High'].iloc[j]); l=float(df['Low'].iloc[j])
                    if o <= entry*(1+STOP): exit_price=o; in_until=j; result="LOSS gap"; break
                    if h>=entry*(1+TARGET) and l<=entry*(1+STOP): exit_price=entry*(1+STOP); in_until=j; result="LOSS both"; break
                    if l<=entry*(1+STOP): exit_price=entry*(1+STOP); in_until=j; result="LOSS"; break
                    if h>=entry*(1+TARGET): exit_price=entry*(1+TARGET); in_until=j; result="WIN"; break
                if exit_price is None:
                    exit_price=float(df['Close'].iloc[max_hold]); in_until=max_hold; result="TIME"
                pnl = (exit_price*(1-FEE_SELL) - entry*(1+FEE_BUY))/(entry*(1+FEE_BUY))*100
                eq.append(eq[-1]*(1+pnl/100)); peak=max(peak,eq[-1]); mdd=max(mdd,(peak-eq[-1])/peak*100)
                trades.append({"Date":df.index[i+1].date(),"PnL%":round(pnl,2),"Result":result,"Win":pnl>0})
        if not trades: return {"trades":0,"winrate":0,"net":0,"mdd":0,"details":[]}
        import pandas as pd
        df_t=pd.DataFrame(trades)
        return {"trades":len(trades),"winrate":round(df_t["Win"].mean()*100,1),"net":round((eq[-1]-1)*100,2),"mdd":round(mdd,2),"details":trades}
    full=run_period(25,len(df)); train=run_period(25,split); test=run_period(split,len(df))
    return {"ticker":ticker,"full":full,"train":train,"test":test}

tab1,tab2 = st.tabs(["LIVE TODAY","BACKTEST v76.2"])
with tab1:
    rows=[]
    for t in STOCKS:
        df=get_data(t,"3mo"); rows.append({"Stock":t,"Score":calculate_score(df),"Signal":"BUY" if calculate_score(df)>=THRESHOLD else "WAIT"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)
with tab2:
    st.write("FIXES: True High shift(1), boundary fix inside period, 1Y not 2Y to avoid timeout")
    results=[]
    for t in STOCKS:
        r=backtest_stock(t)
        if r: results.append(r)
    summ=[]
    for r in results:
        summ.append({"Stock":r["ticker"],"Trades":r["full"]["trades"],"WR%":r["full"]["winrate"],"Net%":r["full"]["net"],"MDD%":r["full"]["mdd"],"Tr Test":r["test"]["trades"],"WR Test":r["test"]["winrate"]})
    st.dataframe(pd.DataFrame(summ), use_container_width=True)
    sel=st.selectbox("Detail", STOCKS)
    for r in results:
        if r["ticker"]==sel:
            st.dataframe(pd.DataFrame(r["full"]["details"]).tail(20), use_container_width=True)
