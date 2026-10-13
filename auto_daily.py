import yfinance as yf
import pandas as pd
import os, requests

STOCKS = ["BBCA.JK","BBRI.JK","BMRI.JK","TLKM.JK","ASII.JK","UNVR.JK","ICBP.JK"]
THRESHOLD=61; TARGET=0.015; STOP=-0.007; FEE_BUY=0.0015; FEE_SELL=0.0025

def calculate_score(df):
    if len(df)<20: return 0
    if isinstance(df.columns, pd.MultiIndex): df.columns=df.columns.get_level_values(0)
    close=df['Close']; sma20=close.rolling(20).mean(); sma5=close.rolling(5).mean(); vol_avg=df['Volume'].rolling(20).mean()
    score=50
    if close.iloc[-1]>sma20.iloc[-1]: score+=10
    if sma5.iloc[-1]>sma20.iloc[-1]: score+=10
    if df['Volume'].iloc[-1]>vol_avg.iloc[-1]: score+=5
    if close.pct_change(5).iloc[-1]>0: score+=8
    if close.iloc[-1]>close.rolling(20).min().iloc[-1]*1.02: score+=5
    return min(100,max(0,int(score)))

def backtest_quick(ticker):
    df=yf.download(ticker, period="6mo", interval="1d", progress=False)
    if df.empty: return 0,0,0
    if isinstance(df.columns, pd.MultiIndex): df.columns=df.columns.get_level_values(0)
    df=df.dropna()
    pnl=[]
    in_until=-1
    for i in range(20, len(df)-2):
        if i<=in_until: continue
        if calculate_score(df.iloc[:i+1])>=THRESHOLD:
            entry=float(df['Open'].iloc[i+1])
            exit_price=None
            for j in range(i+2, min(i+12, len(df))):
                ht=float(df['High'].iloc[j])>=entry*(1+TARGET)
                hs=float(df['Low'].iloc[j])<=entry*(1+STOP)
                if ht and hs: exit_price=entry*(1+STOP); in_until=j; break
                elif hs: exit_price=entry*(1+STOP); in_until=j; break
                elif ht: exit_price=entry*(1+TARGET); in_until=j; break
            if exit_price is None:
                exit_price=float(df['Close'].iloc[min(i+11,len(df)-1)]); in_until=min(i+11,len(df)-1)
            pnl_pct=(exit_price*(1-FEE_SELL)-entry*(1+FEE_BUY))/(entry*(1+FEE_BUY))*100
            pnl.append(pnl_pct)
    if not pnl: return 0,0,0
    return len(pnl), sum(1 for x in pnl if x>0)/len(pnl)*100, sum(pnl)

lines=["*ShiningStar v72 FINAL - Audited*","Entry=Next Open, Exit=D+10, Fees in Win, No Overlap\n"]
for t in STOCKS:
    df=yf.download(t, period="3mo", interval="1d", progress=False)
    if isinstance(df.columns, pd.MultiIndex): df.columns=df.columns.get_level_values(0)
    sc=calculate_score(df)
    n,wr,net=backtest_quick(t)
    lines.append(f"{t}: Score {sc} -> {'BUY' if sc>=THRESHOLD else 'WAIT'} | 6mo {n}tr WR {wr:.1f}% Net {net:.2f}%")
msg="\n".join(lines)
print(msg)
token=os.getenv("TELEGRAM_BOT_TOKEN"); chat=os.getenv("TELEGRAM_CHAT_ID")
if token and chat:
    requests.post(f"https://api.telegram.org/bot{token}/sendMessage", data={"chat_id":chat,"text":msg,"parse_mode":"Markdown"})
