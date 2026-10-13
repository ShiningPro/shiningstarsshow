import streamlit as st
import yfinance as yf
import pandas as pd

st.set_page_config(page_title="ShiningStar v73 PROFESSIONAL", layout="wide")
st.title("ShiningStar v73 - PROFESSIONAL Audited")

STOCKS = ["BBCA.JK","BBRI.JK","BMRI.JK","TLKM.JK","ASII.JK","UNVR.JK","ICBP.JK"]
THRESHOLD = 61
TARGET = 0.015
STOP = -0.007
FEE_BUY = 0.0015
FEE_SELL = 0.0025

def calculate_score(df):
    if len(df) < 20: return 0
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    close = df['Close']
    sma20 = close.rolling(20).mean()
    sma5 = close.rolling(5).mean()
    vol_avg = df['Volume'].rolling(20).mean()
    score = 50
    if close.iloc[-1] > sma20.iloc[-1]: score += 10
    if sma5.iloc[-1] > sma20.iloc[-1]: score += 10
    if df['Volume'].iloc[-1] > vol_avg.iloc[-1]: score += 5
    if close.pct_change(5).iloc[-1] > 0: score += 8
    if close.iloc[-1] > close.rolling(20).min().iloc[-1]*1.02: score += 5
    return min(100, max(0, int(score)))

def backtest_stock(ticker):
    df = yf.download(ticker, period="6mo", interval="1d", progress=False)
    if df.empty or len(df) < 40: return None
    if isinstance(df.columns, pd.MultiIndex): df.columns = df.columns.get_level_values(0)
    df = df.dropna()
    # Split point: 4 months train, 2 months test
    split = int(len(df)*0.66)

    def run_period(start_idx, end_idx):
        trades=[]
        equity_curve=[1.0]
        peak=1.0; max_dd=0; in_until=-1
        for i in range(start_idx, end_idx-1):
            if i <= in_until: continue
            if i < 20: continue
            score = calculate_score(df.iloc[:i+1])
            if score >= THRESHOLD:
                if i+1 >= len(df): continue
                entry = float(df['Open'].iloc[i+1])
                entry_date = df.index[i+1]
                # FIX 2 & 3: Check entry day itself
                # If gap open below stop -> exit at open (realistic)
                open_entry_day = float(df['Open'].iloc[i+1])
                high_entry_day = float(df['High'].iloc[i+1])
                low_entry_day = float(df['Low'].iloc[i+1])

                # Gap handling: open already below stop
                if open_entry_day <= entry*(1+STOP):
                    exit_price = open_entry_day # gap down, worse than stop
                    in_until = i+1
                    result = "LOSS (gap open below stop)"
                else:
                    # Check if target/stop hit on entry day itself
                    ht_entry = high_entry_day >= entry*(1+TARGET)
                    hs_entry = low_entry_day <= entry*(1+STOP)
                    if ht_entry and hs_entry:
                        exit_price = entry*(1+STOP)
                        in_until = i+1
                        result = "LOSS (both hit entry day)"
                    elif hs_entry:
                        exit_price = entry*(1+STOP)
                        in_until = i+1
                        result = "LOSS (stop entry day)"
                    elif ht_entry:
                        exit_price = entry*(1+TARGET)
                        in_until = i+1
                        result = "WIN (target entry day)"
                    else:
                        exit_price = None
                        # check next 9 days
                        for j in range(i+2, min(i+12, len(df))):
                            # Gap check
                            if float(df['Open'].iloc[j]) <= entry*(1+STOP):
                                exit_price = float(df['Open'].iloc[j])
                                in_until=j
                                result=f"LOSS (gap open day {j-i})"
                                break
                            ht = float(df['High'].iloc[j]) >= entry*(1+TARGET)
                            hs = float(df['Low'].iloc[j]) <= entry*(1+STOP)
                            if ht and hs:
                                exit_price=entry*(1+STOP); in_until=j; result="LOSS (both hit)"; break
                            elif hs:
                                exit_price=entry*(1+STOP); in_until=j; result="LOSS"; break
                            elif ht:
                                exit_price=entry*(1+TARGET); in_until=j; result="WIN"; break
                        if exit_price is None:
                            exit_price=float(df['Close'].iloc[min(i+11,len(df)-1)])
                            in_until=min(i+11,len(df)-1)
                            result="TIME_EXIT D+10"

                buy_cost=entry*(1+FEE_BUY); sell=exit_price*(1-FEE_SELL)
                pnl_pct=(sell-buy_cost)/buy_cost*100
                equity_curve.append(equity_curve[-1]*(1+pnl_pct/100))
                peak=max(peak, equity_curve[-1])
                dd=(peak-equity_curve[-1])/peak*100
                max_dd=max(max_dd, dd)
                trades.append({"EntryDate":entry_date.date(),"Score":score,"Entry":round(entry,1),"Exit":round(exit_price,1),"Result":result,"PnL%":round(pnl_pct,2),"Win":pnl_pct>0})
        if not trades:
            return {"trades":0,"winrate":0,"net_compounded":0,"max_dd":0,"details":[],"equity":1.0}
        df_t=pd.DataFrame(trades)
        # FIX 1: Compounded, not sum
        net_comp = (equity_curve[-1]-1)*100
        return {"trades":len(trades),"winrate":round(df_t["Win"].mean()*100,1),"net_compounded":round(net_comp,2),"max_dd":round(max_dd,2),"details":trades,"equity":equity_curve[-1]}

    full = run_period(20, len(df))
    train = run_period(20, split)
    test = run_period(split, len(df))

    if not full: return None
    return {"ticker":ticker,"full":full,"train":train,"test":test}

tab1, tab2 = st.tabs(["LIVE TODAY","BACKTEST v73 PROFESSIONAL"])
with tab1:
    rows=[]
    for t in STOCKS:
        df=yf.download(t, period="3mo", interval="1d", progress=False)
        if isinstance(df.columns, pd.MultiIndex): df.columns=df.columns.get_level_values(0)
        rows.append({"Stock":t,"Score":calculate_score(df),"Signal":"BUY" if calculate_score(df)>=THRESHOLD else "WAIT"})
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

with tab2:
    st.write("v73 FIXES: 1=Compounded Net, 2=Entry-day check, 3=Gap handling, 4=Train 4mo / Test 2mo unseen")
    results=[]
    for t in STOCKS:
        with st.spinner(f"Backtesting {t}"):
            r=backtest_stock(t)
            if r: results.append(r)

    summary=[]
    for r in results:
        summary.append({"Stock":r["ticker"],"Trades Full":r["full"]["trades"],"WR% Full":r["full"]["winrate"],"Net% Compounded Full":r["full"]["net_compounded"],"MaxDD%":r["full"]["max_dd"],"Trades Train 4mo":r["train"]["trades"],"WR Train":r["train"]["winrate"],"Trades Test 2mo":r["test"]["trades"],"WR Test (unseen)":r["test"]["winrate"],"Net% Test":r["test"]["net_compounded"]})
    st.dataframe(pd.DataFrame(summary), use_container_width=True)
    st.warning("If Trades Test <5, win rate is not reliable. Need more trades. If WR Test <50%, threshold 61 not valid on unseen data.")
    sel=st.selectbox("Detail", STOCKS)
    for r in results:
        if r["ticker"]==sel:
            st.write(f"FULL {r['ticker']}"); st.dataframe(pd.DataFrame(r["full"]["details"]).tail(20), use_container_width=True)
            st.write(f"UNSEEN TEST 2mo"); st.dataframe(pd.DataFrame(r["test"]["details"]), use_container_width=True)
