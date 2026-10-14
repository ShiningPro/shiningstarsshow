import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="ShiningStar v76 FIXED", layout="wide")
st.title("ShiningStar v76 - FIXED BREAKOUT Audited")

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

def calculate_score(df, mode="WEIGHTED"):
    try:
        if df is None or len(df) < 25: return 0
        if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
        if 'Close' not in df.columns or 'High' not in df.columns or 'Volume' not in df.columns: return 0
        close = df['Close']; high = df['High']; vol = df['Volume']
        if close.isna().all(): return 0
        sma20 = close.rolling(20).mean()
        sma5 = close.rolling(5).mean()
        vol_avg = vol.rolling(20).mean()
        # FIX A: Genuine breakout - previous 20-day HIGH, not close, shifted
        high20_prev = high.rolling(20).max().shift(1)
        r = rsi(close, 14)
        if pd.isna(sma20.iloc[-1]) or pd.isna(vol_avg.iloc[-1]) or pd.isna(r.iloc[-1]) or pd.isna(high20_prev.iloc[-1]): return 0

        if len(df) >=5:
            val5 = float((close.iloc[-5:] * vol.iloc[-5:]).sum())
            if val5 < 5_000_000_000: return 0

        # FIX B: Mandatory filters version
        if mode == "MANDATORY":
            # Must break previous high, must have trend, must have liquidity
            if close.iloc[-1] < high20_prev.iloc[-1] * 0.98: return 0
            if sma5.iloc[-1] <= sma20.iloc[-1]: return 0
            if close.iloc[-1] <= sma20.iloc[-1]: return 0
            # Rank by volume + RSI
            score = 75
            if vol.iloc[-1] >= vol_avg.iloc[-1]*1.5: score += 10
            if 55 <= r.iloc[-1] <= 70: score += 10
            if r.iloc[-1] > 75: score -= 20
            return min(100, max(0, int(score)))
        else:
            # WEIGHTED version - your current but fixed high
            score = 50
            if close.iloc[-1] >= high20_prev.iloc[-1] * 0.98: score += 15
            if close.iloc[-1] > high20_prev.iloc[-1]: score += 5 # extra for true breakout
            if vol.iloc[-1] >= vol_avg.iloc[-1]*1.5: score += 10
            if 55 <= r.iloc[-1] <= 70: score += 10
            if r.iloc[-1] > 75: score -= 15
            if sma5.iloc[-1] > sma20.iloc[-1]: score += 5
            if close.iloc[-1] > sma20.iloc[-1]: score += 5
            if close.pct_change(5).iloc[-1] < 0 and vol.iloc[-1] > vol_avg.iloc[-1]*3: return 45
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

def backtest_stock(ticker, mode="WEIGHTED"):
    df = get_data(ticker, "2y") # FIX: 2 years not 6mo
    if df.empty or len(df) < 100: return None
    split = int(len(df)*0.70)
    def run_period(start_idx, end_idx):
        trades=[]; equity_curve=[1.0]; peak=1.0; max_dd=0; in_until=-1
        wins=[]; losses=[]
        for i in range(start_idx, end_idx-1):
            if i <= in_until or i < 25: continue
            score = calculate_score(df.iloc[:i+1], mode=mode)
            if score >= THRESHOLD:
                if i+1 >= end_idx: continue
                entry = float(df['Open'].iloc[i+1])
                entry_date = df.index[i+1]
                open_e = float(df['Open'].iloc[i+1]); high_e = float(df['High'].iloc[i+1]); low_e = float(df['Low'].iloc[i+1])
                # FIX 1: Boundary - exit must stay inside period
                if open_e <= entry*(1+STOP):
                    exit_price = open_e; in_until = i+1; result = "LOSS (gap open below stop)"
                else:
                    ht_e = high_e >= entry*(1+TARGET); hs_e = low_e <= entry*(1+STOP)
                    if ht_e and hs_e: exit_price = entry*(1+STOP); in_until = i+1; result = "LOSS (both hit entry day)"
                    elif hs_e: exit_price = entry*(1+STOP); in_until = i+1; result = "LOSS (stop entry day)"
                    elif ht_e: exit_price = entry*(1+TARGET); in_until = i+1; result = "WIN (target entry day)"
                    else:
                        exit_price = None
                        # FIX: loop stops at end_idx, not i+12 overflowing into test
                        max_hold = min(i+12, end_idx-1)
                        for j in range(i+2, max_hold+1):
                            if j >= len(df): break
                            if float(df['Open'].iloc[j]) <= entry*(1+STOP):
                                exit_price = float(df['Open'].iloc[j]); in_until=j; result=f"LOSS (gap open day {j-i})"; break
                            ht = float(df['High'].iloc[j]) >= entry*(1+TARGET); hs = float(df['Low'].iloc[j]) <= entry*(1+STOP)
                            if ht and hs: exit_price=entry*(1+STOP); in_until=j; result="LOSS (both hit)"; break
                            elif hs: exit_price=entry*(1+STOP); in_until=j; result="LOSS"; break
                            elif ht: exit_price=entry*(1+TARGET); in_until=j; result="WIN"; break
                        if exit_price is None:
                            # FIX: exit at period end, not beyond
                            exit_price=float(df['Close'].iloc[end_idx-1]); in_until=end_idx-1; result="TIME_EXIT (period end)"
                buy_cost=entry*(1+FEE_BUY); sell=exit_price*(1-FEE_SELL); pnl_pct=(sell-buy_cost)/buy_cost*100
                equity_curve.append(equity_curve[-1]*(1+pnl_pct/100)); peak=max(peak, equity_curve[-1]); dd=(peak-equity_curve[-1])/peak*100; max_dd=max(max_dd, dd)
                if pnl_pct>0: wins.append(pnl_pct)
                else: losses.append(pnl_pct)
                trades.append({"EntryDate":entry_date.date(),"Score":score,"Entry":round(entry,1),"Exit":round(exit_price,1),"Result":result,"PnL%":round(pnl_pct,2),"Win":pnl_pct>0})
        if not trades:
            return {"trades":0,"winrate":0,"net_compounded":0,"max_dd":0,"details":[],"equity":1.0,"avg_win":0,"avg_loss":0,"expectancy":0,"profit_factor":0}
        df_t=pd.DataFrame(trades); net_comp = (equity_curve[-1]-1)*100
        avg_win = np.mean(wins) if wins else 0
        avg_loss = np.mean(losses) if losses else 0
        expectancy = (len(wins)/len(trades)*avg_win + len(losses)/len(trades)*avg_loss) if trades else 0
        profit_factor = (sum(wins)/abs(sum(losses))) if losses and sum(losses)!=0 else 0
        return {"trades":len(trades),"winrate":round(df_t["Win"].mean()*100,1),"net_compounded":round(net_comp,2),"max_dd":round(max_dd,2),"details":trades,"equity":equity_curve[-1],"avg_win":round(avg_win,2),"avg_loss":round(avg_loss,2),"expectancy":round(expectancy,2),"profit_factor":round(profit_factor,2)}
    full = run_period(25, len(df)); train = run_period(25, split); test = run_period(split, len(df))
    if not full: return None
    return {"ticker":ticker,"full":full,"train":train,"test":test}

tab1, tab2 = st.tabs(["LIVE TODAY v76 FIXED","BACKTEST v76 FIXED 2Y"])
with tab1:
    c1,c2 = st.columns(2)
    mode = c1.selectbox("Mode", ["WEIGHTED","MANDATORY"], index=1)
    rows=[]
    for t in STOCKS:
        df = get_data(t, "3mo"); sc = calculate_score(df, mode=mode)
        rows.append({"Stock":t,"Score":sc,"Signal":"BUY" if sc>=THRESHOLD else "WAIT"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

with tab2:
    st.write("v76 FIXES: 1=Boundary fix, 2=True High shift(1), 3=2Y data, 4=Expectancy + PF")
    mode_bt = st.selectbox("Backtest Mode", ["WEIGHTED","MANDATORY"], index=1, key="bt")
    results=[]
    for t in STOCKS:
        with st.spinner(f"Backtesting {t} {mode_bt}"):
            r=backtest_stock(t, mode=mode_bt)
            if r: results.append(r)
    summary=[]
    for r in results:
        summary.append({"Stock":r["ticker"],"Trades Full":r["full"]["trades"],"WR% Full":r["full"]["winrate"],"Net% Full":r["full"]["net_compounded"],"AvgWin":r["full"]["avg_win"],"AvgLoss":r["full"]["avg_loss"],"Expectancy":r["full"]["expectancy"],"PF":r["full"]["profit_factor"],"MaxDD%":r["full"]["max_dd"],"Trades Test":r["test"]["trades"],"WR Test":r["test"]["winrate"],"Net% Test":r["test"]["net_compounded"]})
    st.dataframe(pd.DataFrame(summary), use_container_width=True)
    st.warning("Fixes: High20_prev = High.rolling(20).max().shift(1). Exit loop stops at period end. 2Y data for reliability.")
    sel=st.selectbox("Detail", STOCKS)
    for r in results:
        if r["ticker"]==sel:
            st.write(f"FULL {r['ticker']} {mode_bt}"); st.dataframe(pd.DataFrame(r["full"]["details"]).tail(30), use_container_width=True)
            st.write(f"UNSEEN TEST"); st.dataframe(pd.DataFrame(r["test"]["details"]), use_container_width=True)
