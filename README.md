# Shining Stars Show v70 - 4 Trades/Mo Test

Test IDX first 2 weeks = 4 trades.

## Where to put Telegram data (Telegraph):
1. Telegram -> @BotFather -> /newbot -> copy TOKEN = TELEGRAM_TOKEN
2. Telegram -> @userinfobot -> copy ID = TELEGRAM_CHAT_ID
3. GitHub -> repo -> Settings -> Secrets and variables -> Actions -> New secret
   - TELEGRAM_TOKEN = token
   - TELEGRAM_CHAT_ID = id
4. Actions -> Run workflow -> Telegram arrives in 30 sec

## 4 trades test:
- Mon Thu 15:00 WIB only
- If SKIP (<50%) -> don't count, wait next
- Buy on Stockbit manual, set Sell +1.5% Stop -0.7%
- After 4 BUYs: report W/L -> we calc real win%

## Math:
- Net win +110k, Net lose -110k (cut 21% from -140k)
- Profit margin kept, lose reduced
- 3W1L = +220k / 2 weeks on 10jt