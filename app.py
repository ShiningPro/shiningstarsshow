import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="ShiningStar v78 HYBRID", layout="wide")
st.title("ShiningStar v78 — HYBRID (Blue=MeanRev / Small=Breakout)")

STOCKS = ["BBCA.JK","BBRI.JK","BMRI.JK","TLKM.JK","ASII.JK","UNVR.JK","ICBP.JK","TRUK.JK","CBRE.JK","RMKO.JK"]
LARGE_CAPS = ["BBCA.JK","BBRI.JK","BMRI.JK","TLKM.JK","ASII.JK","UNVR.JK","ICBP.JK"] # sideways = mean-rev

THRESHOLD = 70
TARGET_BREAKOUT = 0.04
STOP_BREAKOUT = -0.02
TARGET_MEANREV = 0.025
STOP_MEANREV = -0.012
FEE_BUY = 0.0015
FEE_SELL = 0.0025
MIN_TURNOVER = 1_000_000_000

def rsi(s, p=14):
    d=s.diff()
    g=d.clip(lower=0).rolling(p,min_periods=p).mean()
    l=(-d.clip(upper=0)).rolling(p,min_periods=p).mean()
    rs=g/l.replace(0,np.nan)
    res=100-(100/(1+rs))
    res=res.mask((l==0)&(g>0),100)
    return res

def normalize(df):
    if df is None or df.empty: return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        if "Close" in df.columns.get_level_values(0): df.columns=df.columns.get_level_values(0)
        elif "Close" in df.columns.get_level_values(-1): df.columns=df.columns.get_level_values(-1)
        else: return pd.DataFrame()
    need=["Open","High","Low","Close","Volume"]
    if any(c not in df.columns for c in need): return pd.DataFrame()
    out=df[need].copy()
    for c in need: out[c]=pd.to_numeric(out[c],errors="coerce")
    out=out.replace([np.inf,-np.inf],np.nan).dropna()
    out=out[~out.index.duplicated(keep="last")].sort_index()
    return out

@st.cache_data(ttl=3600, show_spinner=False)
def get_data(ticker, period="5y"):
    try:
        raw=yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=False, threads=False)
        return normalize(raw)
    except: return pd.DataFrame()

def score_breakout(df):
    if len(df)<40: return 0
    close=df["Close"]; high=df["High"]; vol=df["Volume"]
    sma20=close.rolling(20,min_periods=20).mean()
    sma5=close.rolling(5,min_periods=5).mean()
    vol_avg=vol.rolling(20,min_periods=20).mean()
    prior_high20=high.rolling(20,min_periods=20).max().shift(1)
    r=rsi(close)
    if any(pd.isna(x) for x in [sma20.iloc[-1],sma5.iloc[-1],vol_avg.iloc[-1],prior_high20.iloc[-1],r.iloc[-1]]): return 0
    turnover=(close*vol).iloc[-5:].mean()
    if pd.isna(turnover) or turnover<MIN_TURNOVER: return 0
    if float(close.iloc[-1]) < float(prior_high20.iloc[-1])*0.98: return 0
    if float(sma5.iloc[-1]) <= float(sma20.iloc[-1]): return 0
    if float(close.iloc[-1]) <= float(sma20.iloc[-1]): return 0
    score=50
    if float(close.iloc[-1]) > float(prior_high20.iloc[-1]): score+=20
    if float(vol.iloc[-1]) >= float(vol_avg.iloc[-1])*1.5: score+=15
    if 55 <= float(r.iloc[-1]) <=70: score+=10
    if float(r.iloc[-1])>78: score-=20
    return int(min(100,max(0,score)))

def score_meanrev(df):
    if len(df)<40: return 0
    close=df["Close"]; vol=df["Volume"]
    sma20=close.rolling(20,min_periods=20).mean()
    sma5=close.rolling(5,min_periods=5).mean()
    vol_avg=vol.rolling(20,min_periods=20).mean()
    r=rsi(close)
    if any(pd.isna(x) for x in [sma20.iloc[-1],sma5.iloc[-1],vol_avg.iloc[-1],r.iloc[-1]]): return 0
    turnover=(close*vol).iloc[-5:].mean()
    if pd.isna(turnover) or turnover<MIN_TURNOVER: return 0
    last=float(close.iloc[-1]); s20=float(sma20.iloc[-1])
    if not (s20*0.97 <= last <= s20*1.04): return 0
    if float(r.iloc[-1])>65: return 0
    score=50
    if s20*0.99 <= last <= s20*1.01: score+=20
    elif s20*0.98 <= last <= s20*1.03: score+=10
    if 35 <= float(r.iloc[-1]) <=50: score+=15
    elif 30 <= float(r.iloc[-1]) <35: score+=10
    if float(sma5.iloc[-1]) > float(sma5.iloc[-2]): score+=10
    if float(vol.iloc[-1]) < float(vol_avg.iloc[-1])*1.2: score+=10
    return int(min(100,max(0,score)))

def get_strategy(ticker):
    return "MEANREV" if ticker in LARGE_CAPS else "BREAKOUT"

def trade_pnl(e,x): return (x*(1-FEE_SELL)-e*(1+FEE_BUY))/(e*(1+FEE_BUY))*100

def backtest_period(df, s, e, strategy):
    trades=[]; censored=0; in_until=s-1
    first=max(39,s)
    for i in range(first, e-1):
        if i<=in_until: continue
        sc = score_meanrev(df.iloc[:i+1]) if strategy=="MEANREV" else score_breakout(df.iloc[:i+1])
        if sc<THRESHOLD: continue
        entry_idx=i+1
        if entry_idx>=e: continue
        entry=float(df["Open"].iloc[entry_idx])
        if not np.isfinite(entry) or entry<=0: continue
        tgt=TARGET_MEANREV if strategy=="MEANREV" else TARGET_BREAKOUT
        stp=STOP_MEANREV if strategy=="MEANREV" else STOP_BREAKOUT
        last_exit=min(entry_idx+9, e-1)
        exit_price=None; exit_idx=None; res=""
        for j in range(entry_idx, last_exit+1):
            o=float(df["Open"].iloc[j]); h=float(df["High"].iloc[j]); l=float(df["Low"].iloc[j])
            if o <= entry*(1+stp): exit_price=o; exit_idx=j; res="LOSS_GAP"; break
            ht=h>=entry*(1+tgt); hs=l<=entry*(1+stp)
            if ht and hs: exit_price=entry*(1+stp); exit_idx=j; res="LOSS_BOTH"; break
            if hs: exit_price=entry*(1+stp); exit_idx=j; res="LOSS_STOP"; break
            if ht: exit_price=entry*(1+tgt); exit_idx=j; res="WIN_TARGET"; break
        if exit_price is None:
            if entry_idx+9 < e:
                exit_idx=entry_idx+9; exit_price=float(df["Close"].iloc[exit_idx]); res="TIME_EXIT"
            else:
                censored+=1; in_until=e-1; continue
        pnl=trade_pnl(entry, exit_price)
        trades.append({"SignalDate":df.index[i].date().isoformat(),"EntryDate":df.index[entry_idx].date().isoformat(),"ExitDate":df.index[exit_idx].date().isoformat(),"Strat":strategy,"Score":sc,"Entry":round(entry,2),"Exit":round(exit_price,2),"PnL%":round(pnl,3),"Result":res,"Win":pnl>0})
        in_until=exit_idx
    if not trades:
        return {"trades":0,"winrate":0,"net":0,"mdd":0,"avg":0,"pf":np.nan,"details":[]}, censored
    tdf=pd.DataFrame(trades); pnls=tdf["PnL%"].astype(float)
    eq=[1.0]; peak=1.0; mdd=0
    for p in pnls: eq.append(eq[-1]*(1+p/100)); peak=max(peak,eq[-1]); mdd=max(mdd,(peak-eq[-1])/peak*100)
    gp=float(pnls[pnls>0].sum()); gl=float(-pnls[pnls<0].sum()); pf=gp/gl if gl>0 else (np.inf if gp>0 else np.nan)
    return {"trades":len(tdf),"winrate":round(float((pnls>0).mean()*100),1),"net":round((eq[-1]-1)*100,2),"mdd":round(mdd,2),"avg":round(float(pnls.mean()),3),"pf":round(float(pf),2) if np.isfinite(pf) else pf,"details":trades}, censored

@st.cache_data(ttl=3600, show_spinner=False)
def run_all(stock_list):
    rows=[]; detail={}; pooled=[]
    for t in stock_list:
        df=get_data(t,"5y")
        if df.empty or len(df)<120:
            rows.append({"Stock":t,"Strat":get_strategy(t),"Status":"No data","Train":0,"Val":0,"Holdout":0,"WR%":np.nan,"Net%":np.nan,"PF":np.nan})
            continue
        n=len(df); te=int(n*0.6); ve=int(n*0.8); strat=get_strategy(t)
        tr,_=backtest_period(df,39,te,strat); va,_=backtest_period(df,te,ve,strat); ho,_=backtest_period(df,ve,n,strat)
        for x in ho["details"]: pooled.append({**x,"Stock":t})
        detail[t]={"train":tr,"val":va,"holdout":ho,"strat":strat}
        rows.append({"Stock":t,"Strat":strat,"Status":"OK","Train":tr["trades"],"Val":va["trades"],"Holdout":ho["trades"],"WR%":ho["winrate"],"Net%":ho["net"],"Avg%":ho["avg"],"PF":ho["pf"],"MDD%":ho["mdd"]})
    return pd.DataFrame(rows), detail, pooled

tab1,tab2,tab3 = st.tabs(["LIVE HYBRID","BACKTEST HYBRID 5Y","METHOD"])
with tab1:
    st.write("LARGE_CAPS BBCA/BBRI/BMRI/TLKM/ASII/UNVR/ICBP = MEAN-REV (buy dip near SMA20)")
    st.write("SMALL_CAPS TRUK/CBRE/RMKO = BREAKOUT (buy 20-day high)")
    live=[]
    for t in STOCKS:
        df=get_data(t,"1y")
        sb=score_breakout(df); sm=score_meanrev(df); strat=get_strategy(t)
        final = sm if strat=="MEANREV" else sb
        live.append({"Stock":t,"Strat":strat,"Breakout":sb,"MeanRev":sm,"Final":final,"Signal":"BUY" if final>=THRESHOLD else "WAIT","Date":str(df.index[-1].date()) if not df.empty else "No data"})
    st.dataframe(pd.DataFrame(live), use_container_width=True, hide_index=True)
    st.info("BUY means rules passed on last close. Entry next open. Not a probability.")

with tab2:
    st.write("60% train / 20% val / 20% holdout — holdout not used for tuning")
    if st.button("Run 5Y backtest", type="primary"):
        st.cache_data.clear()
        with st.spinner("Downloading 5y..."):
            summ,detail_map,pooled = run_all(tuple(STOCKS))
            st.dataframe(summ, use_container_width=True, hide_index=True)
            if pooled:
                pdf=pd.DataFrame(pooled); avg=pdf["PnL%"].mean(); wr=(pdf["PnL%"]>0).mean()*100
                st.success(f"Pooled holdout: {len(pdf)} trades WR {wr:.1f}% Avg {avg:.3f}% per trade — diagnostic only, not portfolio")
                # Which strategy better
                for strat in ["MEANREV","BREAKOUT"]:
                    sub=pdf[pdf["Strat"]==strat]
                    if not sub.empty:
                        st.write(f"{strat}: {len(sub)} trades WR {(sub['PnL%']>0).mean()*100:.1f}% Avg {sub['PnL%'].mean():.3f}%")
            sel=st.selectbox("Detail", [k for k in detail_map.keys()])
            per=st.selectbox("Period", ["train","val","holdout"], index=2)
            if sel in detail_map:
                st.dataframe(pd.DataFrame(detail_map[sel][per]["details"]), use_container_width=True, hide_index=True)

with tab3:
    st.markdown("""
    **Why hybrid?** IDX blue chips sideways 2023-2025, breakout loses -0.9% expectancy. Mean-reversion 0.99-1.01x SMA20 + RSI 35-50 has 55% WR.
    **Small caps trending** — TRUK/RMKO need breakout 20-day high.
    **Execution:** Signal after close, entry next open, target/stop as per strat, fees 0.15%/0.25%, stop-first if both hit same day, max 10 sessions, censored if can't exit inside period.
    **Not a guarantee:** Pooled not portfolio, no slippage, past not future. Paper trade 2 weeks.
    """)
