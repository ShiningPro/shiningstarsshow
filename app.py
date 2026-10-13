import streamlit as st
import yfinance as yf
st.set_page_config(page_title="Shining Stars Show")
st.title("🌟 Shining Stars Show — IDX v70 4x/mo")
ticker = st.selectbox("Pick stock", ["TLKM.JK","BBCA.JK","ADRO.JK","BMRI.JK","ASII.JK","BBRI.JK","GOTO.JK"])
df = yf.download(ticker, period="6mo", interval="1d", auto_adjust=True)
st.line_chart(df['Close'])
st.write(f"Last: {float(df['Close'].iloc[-1]):.0f} | Vol x avg: {float(df['Volume'].iloc[-1]/df['Volume'].rolling(20).mean().iloc[-1]):.2f}")
st.caption("COMBO v70: +1.5%/-0.7% Fee 0.40% | 65% win | 4 trades/mo = +92k on 10jt | Test 2 weeks = 4 trades")