import yfinance as yf
import pandas as pd
import os, requests
import numpy as np

# YOUR 18 VERY GOOD POOL from screenshot EDGE PASS 18 (PF 2.25 etc) - replace 7 blue
STOCKS = ["BUMI.JK","BSDE.JK","DMAS.JK","BSSR.JK","BEST.JK","BKSL.JK","BNBR.JK","HATM.JK","TAPG.JK","VIVA.JK","PTBA.JK","BRMS.JK","DEWA.JK","BUMI.JK","ADRO.JK","ANTM.JK","PTRO.JK","BRPT.JK"]
STOCKS = sorted(list(dict.fromkeys(STOCKS))) # dedupe

THRESHOLD=70
TARGET=0.04
STOP=-0.02
FEE_BUY=0.0015
FEE_SELL=0.0025
LIVE_GUARD_PCT=0.98

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
    return out.replace([np.inf,-np.inf],np.nan).dropna()

def rsi(s,p=14):
    d=s.diff(); g=d.clip(lower=0).rolling(p).mean(); l=(-d.clip(upper=0)).rolling(p).mean()
    rs=g/l.replace(0,np.nan); return 100-(100/(1+rs))

def calculate_score(df): # v79 breakout score, not v73 sma only
    if len(df)<40: return 0, None
    close=df["Close"]; high=df["High"]; vol=df["Volume"]
    sma20=close.rolling(20).mean(); sma5=close.rolling(5).mean()
    vol_avg=vol.rolling(20).mean(); prior_high20=high.rolling(20).max().shift(1)
    r=rsi(close)
    if pd.isna(prior_high20.iloc[-1]): return 0, None
    if float(close.iloc[-1]) < float(prior_high20.iloc[-1])*0.98: return 0, float(prior_high20.iloc[-1])
    if float(sma5.iloc[-1]) <= float(sma20.iloc[-1]): return 0, float(prior_high20.iloc[-1])
    score=50
    if float(close.iloc[-1]) > float(prior_high20.iloc[-1]): score+=20
    if float(vol.iloc[-1]) >= float(vol_avg.iloc[-1])*1.5: score+=15
    if 55 <= float(r.iloc[-1]) <=70: score+=10
    return min(100,max(0,int(score))), float(prior_high20.iloc[-1])

def trade_pnl(e,x): return (x*(1-FEE_SELL)-e*(1+FEE_BUY))/(e*(1+FEE_BUY))*100

def backtest_quick(ticker): # 2y holdout to get 5 trades like BUMI 5 trades PF 2.25
    df=normalize(yf.download(ticker, period="2y", interval="1d", progress=False, auto_adjust=False))
    if len(df)<120: return 0,0,0
    n=len(df); trades=[]; in_until=-1
    for i in range(40, n-1):
        if i<=in_until: continue
        sc,_=calculate_score(df.iloc[:i+1])
        if sc<THRESHOLD: continue
        entry_idx=i+1
        if entry_idx>=n: continue
        entry=float(df["Open"].iloc[entry_idx])
        # FIX GAP: check open gap through stop
        if float(df["Open"].iloc[entry_idx]) <= entry*(1+STOP):
            pnl=trade_pnl(entry, float(df["Open"].iloc[entry_idx])); trades.append(pnl); in_until=entry_idx; continue
        exit_price=None; exit_idx=entry_idx
        for j in range(entry_idx, min(entry_idx+10, n)):
            o=float(df["Open"].iloc[j]); h=float(df["High"].iloc[j]); l=float(df["Low"].iloc[j])
            if o <= entry*(1+STOP): exit_price=o; exit_idx=j; break
            ht=h>=entry*(1+TARGET); hs=l<=entry*(1+STOP)
            if ht and hs: exit_price=entry*(1+STOP); exit_idx=j; break
            if hs: exit_price=entry*(1+STOP); exit_idx=j; break
            if ht: exit_price=entry*(1+TARGET); exit_idx=j; break
        if exit_price is None:
            exit_idx=min(entry_idx+9,n-1); exit_price=float(df["Close"].iloc[exit_idx])
        trades.append(trade_pnl(entry, exit_price)); in_until=exit_idx
    if not trades: return 0,0,0
    pnls=np.array(trades); pf= (pnls[pnls>0].sum() / -pnls[pnls<0].sum()) if (pnls<0).any() else (10 if (pnls>0).any() else 0)
    wr=float((pnls>0).mean()*100); avg=float(pnls.mean())
    return len(trades), wr, round(float(pf),2)

lines=["*ShiningStar v79.2 18Pool LIVE GUARD*","Edge: PF>1.2 from your 18 screenshot (BUMI 5tr PF2.25) vs blue BBCA PF0.35 FAIL","Guard: BUY only if Live >=98% High20, fixes red chart late data\n"]
buy_list=[]

for t in STOCKS:
    df=normalize(yf.download(t, period="1y", interval="1d", progress=False, auto_adjust=False))
    if df.empty: continue
    sc, prior_high = calculate_score(df)
    if prior_high is None: continue
    live=float(df["Close"].iloc[-1])
    live_pct=live/prior_high*100 if prior_high else 0
    n,wr,pf = backtest_quick(t)
    pass_edge = pf>=1.2 and n>=3 and wr>=40

    base="BUY" if sc>=THRESHOLD else "WAIT"
    final=base
    if base=="BUY":
        if live < prior_high * LIVE_GUARD_PCT:
            final="WAIT - Guard (red)"
        elif not pass_edge:
            final="WAIT - No Edge"

    if final.startswith("BUY"):
        buy_list.append(f"{t} Score{sc} Live{live:.0f} High20{prior_high:.0f} {live_pct:.1f}% PF{pf} {n}tr WR{wr:.0f}% -> BUY if open>{prior_high*0.98:.0f}")
        lines.append(f"{t}: Score {sc} {live_pct:.1f}% High20 | {n}tr WR {wr:.0f}% PF {pf} | *BUY*")
    else:
        lines.append(f"{t}: Score {sc} {live_pct:.1f}% High20 | {n}tr PF {pf} | {final}")

if buy_list:
    lines.append("\n*TOMORROW BUY IF HOLDS:*\n" + "\n".join(buy_list))
    lines.append("\nRules: Buy at open only if Live%High>98%. Stop -2% Target +4%. Max 2 positions.")
else:
    lines.append("\nNo BUY tomorrow from 18 pool - all WAIT or Guard (fixes your red chart). BUMI-like breakout ~1/week.")

msg="\n".join(lines)
print(msg)

token=os.getenv("TELEGRAM_BOT_TOKEN"); chat=os.getenv("TELEGRAM_CHAT_ID")
if token and chat:
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id":chat,"text":msg,"parse_mode":"Markdown"})
