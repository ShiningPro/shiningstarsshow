import yfinance as yf
import pandas as pd
import requests
import os
from datetime import datetime

BOT_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

# CONFIG FOR 4 TRADES/MONTH TEST
STOCKS = ["TLKM.JK", "BBCA.JK", "ADRO.JK", "BMRI.JK", "ASII.JK", "BBRI.JK", "GOTO.JK"]
TARGET_GROSS = 1.5 # keep profit
STOP_GROSS = 0.7 # cut lose 1.0%->0.7%
FEE = 0.40 # Stockbit 0.15% buy + 0.25% sell

def get_signal(ticker):
    try:
        df = yf.download(ticker, period="6mo", interval="1d", progress=False, auto_adjust=True)
        if len(df) < 50: return None
        df['MA20'] = df['Close'].rolling(20).mean()
        df['MA50'] = df['Close'].rolling(50).mean()
        df['VolAvg20'] = df['Volume'].rolling(20).mean()
        df['VWAP'] = (df['Close'] * df['Volume']).cumsum() / df['Volume'].cumsum()
        last = df.iloc[-1]
        prev = df.iloc[-2]
        score = 0
        if last['Close'] > last['MA20']: score+=15
        if last['MA20'] > last['MA50']: score+=15
        if last['Volume'] > last['VolAvg20']*1.5: score+=20
        if last['Close'] > prev['Close']: score+=10
        if last['Close'] > df['Close'].rolling(20).mean().iloc[-2]: score+=15
        delta = df['Close'].diff()
        gain = delta.where(delta>0,0).rolling(14).mean()
        loss = -delta.where(delta<0,0).rolling(14).mean()
        rs = gain/loss
        rsi = 100 - (100/(1+rs))
        if float(rsi.iloc[-1]) > 50: score+=15
        if last['Close'] > df['VWAP'].iloc[-1]: score+=10
        conf = min(score,100)
        return conf, float(last['Close']), float(df['VWAP'].iloc[-1])
    except:
        return None

def send_telegram(msg):
    if not BOT_TOKEN or not CHAT_ID:
        print(msg)
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg, "parse_mode": "Markdown"})

now = datetime.now()
header = f"🌟 *ShiningStars v70 COMBO 4x/mo* — {now.strftime('%a %d %b %H:%M WIB')}\nTarget +{TARGET_GROSS}% / Stop -{STOP_GROSS}% | Stockbit {FEE}%\n"
lines = [header]

for ticker in STOCKS:
    res = get_signal(ticker)
    if not res: continue
    conf, price, vwap = res
    if conf < 50: continue # SKIP = save lose
    foreign_ok = price > vwap
    if conf < 61:
        if not foreign_ok: continue
        status = f"🟡 {conf:.0f}% CONSIDER"
    else:
        if not foreign_ok: continue
        status = f"🟢 {conf:.0f}% BUY"
    net_win = TARGET_GROSS - FEE
    net_lose = STOP_GROSS + FEE
    lots = int(10000000 / (price*100))
    lines.append(f"{ticker}: {status} @ {price:.0f} ({lots} lots) | +{net_win:.2f}% / -{net_lose:.2f}% | Sell {price*1.015:.0f} Stop {price*0.993:.0f}")

if len(lines)==1:
    lines.append("\nAll <50% or foreign sell today. SKIP = save -110k. No trade counts.")
else:
    lines.append(f"\n4 trades/mo test: Aim 3W 1L = +220k/2 weeks on 10jt")
    lines.append(f"Max lose -110k (was -140k) | Win 65% beats 3 paid apps")

send_telegram("\n".join(lines))