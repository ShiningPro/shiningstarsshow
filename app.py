import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="ShiningStar v79.1 Live Guard", layout="wide")
st.title("ShiningStar v79.1 — PF Filter + Live Price Guard (Fix Late Data)")

DEFAULT_STOCKS = [
"BBCA.JK","BBRI.JK","BMRI.JK","TLKM.JK","ASII.JK","UNVR.JK","ICBP.JK",
"TRUK.JK","CBRE.JK","RMKO.JK",
"GOTO.JK","BUKA.JK","ESSA.JK","ADRO.JK","PTBA.JK","ANTM.JK","INCO.JK",
"BRMS.JK","DEWA.JK","BUMI.JK"
]

TARGET=0.04
STOP=-0.02
FEE_BUY=0.0015
FEE_SELL=0.0025
MIN_TURNOVER=1_000_000_000
THRESHOLD=70
LIVE_GUARD_PCT=0.98 # If live price < 98% of prior high20, breakout failed intraday -> WAIT

def rsi(s,p=14):
    d=s.diff(); g=d.clip(lower=0).rolling(p,min_periods=p).mean(); l=(-d.clip(upper=0)).rolling(p,min_periods=p).mean()
    rs=g/l.replace(0,np.nan); res=100-(100/(1+rs)); res=res.mask((l==0)&(g>0),100); return res

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

@st.cache_data(ttl=300, show_spinner=False) # 5 min cache for live
def get_data(ticker, period="5y"):
    try:
        raw=yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=False, threads=False)
        return normalize(raw)
    except: return pd.DataFrame()

def score_breakout(df):
    if len(df)<40: return 0, None
    close=df["Close"]; high=df["High"]; vol=df["Volume"]
    sma20=close.rolling(20,min_periods=20).mean(); sma5=close.rolling(5,min_periods=5).mean()
    vol_avg=vol.rolling(20,min_periods=20).mean(); prior_high20=high.rolling(20,min_periods=20).max().shift(1)
    r=rsi(close)
    if any(pd.isna(x) for x in [sma20.iloc[-1],sma5.iloc[-1],vol_avg.iloc[-1],prior_high20.iloc[-1],r.iloc[-1]]): return 0, None
    if (close*vol).iloc[-5:].mean() < MIN_TURNOVER: return 0, float(prior_high20.iloc[-1])
    if float(close.iloc[-1]) < float(prior_high20.iloc[-1])*0.98: return 0, float(prior_high20.iloc[-1])
    if float(sma5.iloc[-1]) <= float(sma20.iloc[-1]): return 0, float(prior_high20.iloc[-1])
    score=50
    if float(close.iloc[-1]) > float(prior_high20.iloc[-1]): score+=20
    if float(vol.iloc[-1]) >= float(vol_avg.iloc[-1])*1.5: score+=15
    if 55 <= float(r.iloc[-1]) <=70: score+=10
    if float(r.iloc[-1])>78: score-=20
    return int(min(100,max(0,score))), float(prior_high20.iloc[-1])

def trade_pnl(e,x): return (x*(1-FEE_SELL)-e*(1+FEE_BUY))/(e*(1+FEE_BUY))*100

def backtest_holdout(df):
    n=len(df)
    if n<120: return None
    te=int(n*0.6); ve=int(n*0.8); s=ve; e=n; trades=[]; in_until=s-1
    for i in range(max(39,s), e-1):
        if i<=in_until: continue
        sc,_=score_breakout(df.iloc[:i+1])
        if sc < THRESHOLD: continue
        entry_idx=i+1; entry=float(df["Open"].iloc[entry_idx]); last_exit=min(entry_idx+9, e-1)
        exit_price=None; exit_idx=None
        for j in range(entry_idx, last_exit+1):
            o=float(df["Open"].iloc[j]); h=float(df["High"].iloc[j]); l=float(df["Low"].iloc[j])
            if o <= entry*(1+STOP): exit_price=o; exit_idx=j; break
            ht=h>=entry*(1+TARGET); hs=l<=entry*(1+STOP)
            if ht and hs: exit_price=entry*(1+STOP); exit_idx=j; break
            if hs: exit_price=entry*(1+STOP); exit_idx=j; break
            if ht: exit_price=entry*(1+TARGET); exit_idx=j; break
        if exit_price is None:
            if entry_idx+9 < e: exit_idx=entry_idx+9; exit_price=float(df["Close"].iloc[exit_idx])
            else: continue
        pnl=trade_pnl(entry, exit_price); trades.append(pnl); in_until=exit_idx
    if len(trades)<1: return {"trades":0,"winrate":0,"net":0,"pf":0,"avg":0,"mdd":0}
    pnls=np.array(trades); eq=[1.0]; peak=1.0; mdd=0
    for p in pnls: eq.append(eq[-1]*(1+p/100)); peak=max(peak,eq[-1]); mdd=max(mdd,(peak-eq[-1])/peak*100)
    gp=float(pnls[pnls>0].sum()); gl=float(-pnls[pnls<0].sum()); pf=gp/gl if gl>0 else (10.0 if gp>0 else 0)
    net=(eq[-1]-1)*100; wr=float((pnls>0).mean()*100); avg=float(pnls.mean())
    return {"trades":len(trades),"winrate":round(wr,1),"net":round(net,2),"pf":round(float(pf),2),"avg":round(avg,3),"mdd":round(mdd,2)}

tab_scan, tab_live, tab_explain = st.tabs(["1. 900 SCANNER","2. LIVE WITH GUARD","EXPLAIN"])

with tab_scan:
    st.write("Set filters to find BUMI/PTBA like stocks. Use Min Trades=5 for small caps.")
    txt=st.text_area("Stock list (paste 900)", value=",".join(DEFAULT_STOCKS), height=80)
    stocks=[s.strip().upper() for s in txt.replace("\n",",").split(",") if s.strip()]
    stocks=list(dict.fromkeys(stocks))[:900]
    c1,c2,c3,c4=st.columns(4)
    min_trades=c1.slider("Min Trades",1,20,5)
    min_pf=c2.slider("Min PF",0.5,3.0,1.2,0.1)
    min_wr=c3.slider("Min WR%",10,60,40)
    max_mdd=c4.slider("Max MDD%",10,60,30)
    if st.button("Run 5Y Scanner", type="primary"):
        results=[]; prog=st.progress(0)
        for idx,t in enumerate(stocks):
            prog.progress((idx+1)/len(stocks))
            df=get_data(t,"5y"); m=backtest_holdout(df)
            if m is None: continue
            results.append({"Stock":t,**m})
        prog.empty()
        df_res=pd.DataFrame(results)
        if df_res.empty: st.warning("No data")
        else:
            filtered=df_res[(df_res["pf"]>=min_pf)&(df_res["net"]>0)&(df_res["winrate"]>=min_wr)&(df_res["mdd"]<=max_mdd)&(df_res["trades"]>=min_trades)].sort_values("pf",ascending=False)
            st.dataframe(df_res.sort_values("pf",ascending=False), use_container_width=True, hide_index=True)
            st.subheader(f"EDGE PASS = {len(filtered)} stocks (your good pool)")
            st.dataframe(filtered, use_container_width=True, hide_index=True)
            st.session_state["edge_list"]=filtered["Stock"].tolist()
            st.session_state["edge_df"]=filtered

with tab_live:
    st.write(f"Live guard: If live price < {LIVE_GUARD_PCT*100:.0f}% of prior 20d high, BUY -> WAIT (breakout failed intraday). Fixes red chart late data.")
    st.caption("Daily yfinance is delayed 15min + final after close 16:00 WIB. Guard prevents buying when chart already red.")
    edge_list=st.session_state.get("edge_list", DEFAULT_STOCKS)
    st.write(f"Checking {len(edge_list)} stocks from edge pool (or default 20 if scanner not run)")
    if st.button("Refresh Live Now", type="primary"):
        st.cache_data.clear()
    rows=[]
    for t in edge_list[:60]: # limit 60 for speed
        df=get_data(t,"1y")
        if df.empty: continue
        sc, prior_high = score_breakout(df)
        m=backtest_holdout(get_data(t,"5y"))
        if m is None: continue
        live_price=float(df["Close"].iloc[-1])
        live_vs_high = (live_price/prior_high*100) if prior_high else 0
        pass_edge = (m["pf"]>=1.2 and m["net"]>0 and m["winrate"]>=40 and m["trades"]>=5)
        # base signal
        base_signal = "BUY" if sc>=THRESHOLD else "WAIT"
        final_signal=base_signal
        reason=""
        if base_signal=="BUY":
            if live_price < prior_high * LIVE_GUARD_PCT:
                final_signal="WAIT - Guard"
                reason=f"Live {live_price:.0f} < {LIVE_GUARD_PCT*100:.0f}% of High20 {prior_high:.0f} ({live_vs_high:.1f}%) - chart red, breakout failed"
            elif not pass_edge:
                final_signal="WAIT - No Edge"
                reason=f"PF {m['pf']} trades {m['trades']} fails edge filter"
        else:
            reason=f"Score {sc}<{THRESHOLD} or live {live_vs_high:.1f}% of High20"
        rows.append({"Stock":t,"Score":sc,"Live":live_price,"High20":round(prior_high,0) if prior_high else 0,"Live%High":round(live_vs_high,1),"PF":m["pf"],"Net%":m["net"],"WR%":m["winrate"],"Trades":m["trades"],"Base":base_signal,"Final":final_signal,"Reason":reason})
    df_live=pd.DataFrame(rows).sort_values("PF",ascending=False)
    st.dataframe(df_live, use_container_width=True, hide_index=True)
    st.info("BUMI/PTBA example: If Score 0, Live%High <100% - WAIT correct. If Score 70 but Live%High 96% red, Final becomes WAIT - Guard, saving you from buying top that already failed.")

with tab_explain:
    st.markdown("""
    **Why your data late:**
    - yfinance daily = yesterday close until 16:00 today close finalized
    - You see TradingView red at 10:30, but yfinance still shows yesterday
    - v79.1 guard checks Live%High: if live <98% of High20, force WAIT

    **How to use for BUMI/PTBA:**
    1. Run Scanner with Min Trades 5 -> BUMI PF 2.25, PTBA PF 6.36 PASS
    2. Go LIVE WITH GUARD -> Refresh after 09:30
    3. If Final=BUY, buy at next 5-min candle, not at delayed daily close
    4. If Final=WAIT - Guard, means breakout already red, skip today

    **Rule for IDX blue vs small:**
    Blue BBRI PF 0.25 Net -10% never passes edge, always WAIT. Small BUMI/PTBA PF>2 passes, only BUY when Live%High >98%.
    """)
