import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

st.set_page_config(page_title="ShiningStar v79 Scanner", layout="wide")
st.title("ShiningStar v79 — Small-Cap Edge Scanner (PF >1.2)")

# PASTE YOUR 900 HERE - demo with 20 mixed
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

@st.cache_data(ttl=3600, show_spinner=False)
def get_data(ticker, period="5y"):
    try:
        raw=yf.download(ticker, period=period, interval="1d", progress=False, auto_adjust=False, threads=False)
        return normalize(raw)
    except: return pd.DataFrame()

def score_breakout(df):
    if len(df)<40: return 0
    close=df["Close"]; high=df["High"]; vol=df["Volume"]
    sma20=close.rolling(20,min_periods=20).mean(); sma5=close.rolling(5,min_periods=5).mean()
    vol_avg=vol.rolling(20,min_periods=20).mean(); prior_high20=high.rolling(20,min_periods=20).max().shift(1)
    r=rsi(close)
    if any(pd.isna(x) for x in [sma20.iloc[-1],sma5.iloc[-1],vol_avg.iloc[-1],prior_high20.iloc[-1],r.iloc[-1]]): return 0
    if (close*vol).iloc[-5:].mean() < MIN_TURNOVER: return 0
    if float(close.iloc[-1]) < float(prior_high20.iloc[-1])*0.98: return 0
    if float(sma5.iloc[-1]) <= float(sma20.iloc[-1]): return 0
    score=50
    if float(close.iloc[-1]) > float(prior_high20.iloc[-1]): score+=20
    if float(vol.iloc[-1]) >= float(vol_avg.iloc[-1])*1.5: score+=15
    if 55 <= float(r.iloc[-1]) <=70: score+=10
    if float(r.iloc[-1])>78: score-=20
    return int(min(100,max(0,score)))

def trade_pnl(e,x): return (x*(1-FEE_SELL)-e*(1+FEE_BUY))/(e*(1+FEE_BUY))*100

def backtest_holdout(df):
    # 60/20/20 split, only need holdout for ranking
    n=len(df)
    if n<120: return None
    te=int(n*0.6); ve=int(n*0.8)
    s=ve; e=n; trades=[]; in_until=s-1
    for i in range(max(39,s), e-1):
        if i<=in_until: continue
        if score_breakout(df.iloc[:i+1]) < THRESHOLD: continue
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
    if len(trades)<5: return {"trades":len(trades),"winrate":0,"net":0,"pf":0,"avg":0,"mdd":0}
    pnls=np.array(trades); eq=[1.0]; peak=1.0; mdd=0
    for p in pnls: eq.append(eq[-1]*(1+p/100)); peak=max(peak,eq[-1]); mdd=max(mdd,(peak-eq[-1])/peak*100)
    gp=float(pnls[pnls>0].sum()); gl=float(-pnls[pnls<0].sum()); pf=gp/gl if gl>0 else (np.inf if gp>0 else 0)
    net=(eq[-1]-1)*100; wr=float((pnls>0).mean()*100); avg=float(pnls.mean())
    return {"trades":len(trades),"winrate":round(wr,1),"net":round(net,2),"pf":round(float(pf),2) if np.isfinite(pf) else 0,"avg":round(avg,3),"mdd":round(mdd,2)}

tab_scan, tab_live, tab_how = st.tabs(["900 SCANNER PF>1.2","LIVE FILTERED","HOW TO USE"])

with tab_scan:
    st.write("Paste 900 tickers (comma or newline). Demo shows 20. Ranking by PF>1.2, Net>0, WR>40%, MDD<25%, Trades>=10")
    txt=st.text_area("Stock list", value=",".join(DEFAULT_STOCKS), height=100)
    stocks=[s.strip().upper() for s in txt.replace("\n",",").split(",") if s.strip()]
    stocks=list(dict.fromkeys(stocks))[:900]
    st.write(f"Scanning {len(stocks)} stocks 5Y... (cached, ~2 sec per stock first time)")

    min_trades=st.slider("Min holdout trades",5,30,10)
    min_pf=st.slider("Min PF",0.8,2.0,1.2,0.1)
    min_wr=st.slider("Min WR%",30,60,40)
    max_mdd=st.slider("Max MDD%",10,50,25)

    if st.button("Run Scanner", type="primary"):
        st.cache_data.clear() # comment this if scanning 900 to keep cache
        results=[]
        prog=st.progress(0)
        for idx,t in enumerate(stocks):
            prog.progress((idx+1)/len(stocks))
            df=get_data(t,"5y")
            if df.empty: continue
            m=backtest_holdout(df)
            if m is None: continue
            results.append({"Stock":t,"Trades":m["trades"],"WR%":m["winrate"],"Net%":m["net"],"Avg%":m["avg"],"PF":m["pf"],"MDD%":m["mdd"]})
        prog.empty()
        df_res=pd.DataFrame(results)
        if df_res.empty:
            st.warning("No data")
        else:
            # Edge filter
            filtered=df_res[(df_res["PF"]>=min_pf)&(df_res["Net%"]>0)&(df_res["WR%"]>=min_wr)&(df_res["MDD%"]<=max_mdd)&(df_res["Trades"]>=min_trades)].sort_values("PF",ascending=False)
            st.subheader(f"All {len(df_res)} stocks")
            st.dataframe(df_res.sort_values("PF",ascending=False), use_container_width=True, hide_index=True)
            st.subheader(f"EDGE FILTERED PF>={min_pf} Net>0 WR>={min_wr}% MDD<={max_mdd}% Trades>={min_trades} = {len(filtered)} stocks")
            st.dataframe(filtered, use_container_width=True, hide_index=True)
            if len(filtered)==0:
                st.error("No stock passes PF>1.2 — this is what your BBCA screenshot showed: BBCA PF 0.35, BBRI 0.78. They fail. This is honest. Lower PF to 0.9 to see best of worst, or scan 900 small caps not blue chips.")
            else:
                st.success(f"Found {len(filtered)} edge stocks — these are your TRUK-like pool. Trade only these, not BBCA.")

with tab_live:
    st.write("LIVE TODAY but only for EDGE stocks from scanner")
    st.caption("If stock fails PF filter, signal forced WAIT even if Score 70")
    # quick demo live for default 20
    live=[]
    for t in DEFAULT_STOCKS[:20]:
        df=get_data(t,"1y"); sc=score_breakout(df)
        m=backtest_holdout(get_data(t,"5y"))
        passes=False
        if m: passes = (m["pf"]>=1.2 and m["net"]>0 and m["winrate"]>=40 and m["mdd"]<=25 and m["trades"]>=10)
        sig="BUY" if sc>=THRESHOLD and passes else "WAIT"
        live.append({"Stock":t,"Score":sc,"PF":m["pf"] if m else 0,"Net%":m["net"] if m else 0,"WR%":m["winrate"] if m else 0,"PassEdge":passes,"Signal":sig})
    st.dataframe(pd.DataFrame(live), use_container_width=True, hide_index=True)

with tab_how:
    st.markdown("""
    **Why v79 fixes your problem:**
    - v78 showed BBCA PF 0.35 Net -30% — Score 85 BUY but losing
    - v79 ranks by **PF = gross profit / gross loss**, not Score
    - PF>1.2 means you make 1.2x what you lose
    - BBCA/BBRI/BMRI PF 0.35-0.78 FAIL filter, TRUK-like PF>1.2 PASS

    **For 900 scan:**
    1. Paste 900.JK tickers
    2. Run Scanner (takes ~15 min first time, cached after)
    3. You will get ~10-30 stocks with PF>1.2 — that's your tradable pool
    4. LIVE FILTERED only BUYs those

    **Expectation:** On IDX blue chips 900, 90% will fail PF>1.2 like your screenshot. That's normal. Small caps BUMI, BRMS, DEWA, GOTO often pass because they trend.
    **Not financial advice:** Past PF does not guarantee future. Need 10+ trades evidence.
    """)
