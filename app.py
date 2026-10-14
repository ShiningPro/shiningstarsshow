import streamlit as st
import yfinance as yf
import pandas as pd
import numpy as np

# ShiningStar v77 - Research / validation build
# Important: this is a research tool, not a guarantee of future profits.
st.set_page_config(page_title="ShiningStar v77 - Validated Breakout", layout="wide")
st.title("ShiningStar v77 — Breakout Research & Validation")
st.caption(
    "Signals use daily closing data and enter at the next session's open. "
    "Backtests include estimated fees, conservative same-day stop/target handling, "
    "and chronological train/validation/holdout periods."
)

STOCKS = [
    "BBCA.JK", "BBRI.JK", "BMRI.JK", "TLKM.JK", "ASII.JK",
    "UNVR.JK", "ICBP.JK", "TRUK.JK", "CBRE.JK", "RMKO.JK"
]

# Keep these fixed before examining the final holdout results.
DATA_PERIOD = "5y"
THRESHOLD = 70
TARGET = 0.04
STOP = -0.02
FEE_BUY = 0.0015
FEE_SELL = 0.0025
MIN_AVG_TURNOVER_IDR = 1_000_000_000  # average daily turnover proxy
VOLUME_MULTIPLE = 1.5
MAX_HOLD_SESSIONS = 10
MIN_TEST_TRADES_FOR_EVIDENCE = 30  # pooled trades are still not independent

st.sidebar.header("Strategy settings")
st.sidebar.write(f"History: {DATA_PERIOD}")
st.sidebar.write(f"Score threshold: {THRESHOLD}")
st.sidebar.write(f"Target / stop: +{TARGET:.0%} / {STOP:.0%}")
st.sidebar.write(f"Estimated buy / sell fees: {FEE_BUY:.2%} / {FEE_SELL:.2%}")
st.sidebar.caption(
    "Do not tune settings based on the final holdout and then continue calling it unseen."
)


def rsi(series, period=14):
    """Wilder-like simple rolling RSI, matching the project's prior approach."""
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period, min_periods=period).mean()
    loss = (-delta.clip(upper=0)).rolling(period, min_periods=period).mean()
    rs = gain / loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    # If there were no losses in the period, RSI is conventionally 100.
    result = result.mask((loss == 0) & (gain > 0), 100)
    return result


def normalize_download(df):
    if df is None or df.empty:
        return pd.DataFrame()
    if isinstance(df.columns, pd.MultiIndex):
        # yfinance can return ticker/field or field/ticker multi-index columns.
        if "Close" in df.columns.get_level_values(0):
            df.columns = df.columns.get_level_values(0)
        elif "Close" in df.columns.get_level_values(-1):
            df.columns = df.columns.get_level_values(-1)
        else:
            return pd.DataFrame()
    needed = ["Open", "High", "Low", "Close", "Volume"]
    if any(c not in df.columns for c in needed):
        return pd.DataFrame()
    out = df[needed].copy()
    for c in needed:
        out[c] = pd.to_numeric(out[c], errors="coerce")
    out = out.replace([np.inf, -np.inf], np.nan).dropna()
    out = out[~out.index.duplicated(keep="last")].sort_index()
    return out


@st.cache_data(ttl=3600, show_spinner=False)
def get_data(ticker, period=DATA_PERIOD):
    try:
        raw = yf.download(
            ticker,
            period=period,
            interval="1d",
            progress=False,
            auto_adjust=False,
            threads=False
        )
        return normalize_download(raw)
    except Exception:
        return pd.DataFrame()


def calculate_score(df):
    """
    Eligibility filters:
      - enough valid history
      - average turnover proxy >= minimum
      - close is within 2% of the previous 20-session high
      - short trend is positive and close is above SMA20

    Score after eligibility:
      50 base + 20 actual close breakout + 15 relative volume + 10 healthy RSI
      -20 overbought RSI penalty.
    Threshold 70 means a setup generally needs a confirmed close breakout or
    a combination of supporting volume/momentum. The threshold is not a
    probability of winning.
    """
    if df is None or len(df) < 40:
        return 0

    try:
        df = normalize_download(df)
        if len(df) < 40:
            return 0

        close = df["Close"]
        high = df["High"]
        vol = df["Volume"]

        sma20 = close.rolling(20, min_periods=20).mean()
        sma5 = close.rolling(5, min_periods=5).mean()
        vol_avg = vol.rolling(20, min_periods=20).mean()
        prior_high20 = high.rolling(20, min_periods=20).max().shift(1)
        r = rsi(close, 14)

        values = [sma20.iloc[-1], sma5.iloc[-1], vol_avg.iloc[-1],
                  prior_high20.iloc[-1], r.iloc[-1]]
        if any(pd.isna(x) for x in values):
            return 0

        # Average daily traded-value proxy, not exact exchange turnover.
        turnover = close * vol
        avg_turnover = turnover.iloc[-5:].mean()
        if pd.isna(avg_turnover) or avg_turnover < MIN_AVG_TURNOVER_IDR:
            return 0

        last_close = float(close.iloc[-1])
        prior_high = float(prior_high20.iloc[-1])

        # Mandatory setup filters.
        if prior_high <= 0 or last_close < prior_high * 0.98:
            return 0
        if float(sma5.iloc[-1]) <= float(sma20.iloc[-1]):
            return 0
        if last_close <= float(sma20.iloc[-1]):
            return 0

        score = 50

        # Confirmed close above the previous 20-session high.
        if last_close > prior_high:
            score += 20

        # Relative volume confirmation.
        if float(vol.iloc[-1]) >= float(vol_avg.iloc[-1]) * VOLUME_MULTIPLE:
            score += 15

        # Healthy momentum, without requiring RSI to be in this band.
        if 55 <= float(r.iloc[-1]) <= 70:
            score += 10

        # Avoid chasing extremely stretched momentum.
        if float(r.iloc[-1]) > 78:
            score -= 20

        return int(min(100, max(0, score)))
    except Exception:
        return 0


def trade_pnl(entry, exit_price):
    buy_cost = entry * (1 + FEE_BUY)
    sell_proceeds = exit_price * (1 - FEE_SELL)
    return (sell_proceeds - buy_cost) / buy_cost * 100


def summarize_trades(trades, benchmark_return=None):
    if not trades:
        return {
            "trades": 0, "winrate": 0.0, "net": 0.0, "mdd": 0.0,
            "avg_trade": 0.0, "profit_factor": np.nan, "gross_profit": 0.0,
            "gross_loss": 0.0, "benchmark": benchmark_return, "details": [],
            "equity": 1.0
        }

    tdf = pd.DataFrame(trades)
    pnls = tdf["PnL%"].astype(float)
    equity = [1.0]
    peak = 1.0
    mdd = 0.0
    for pnl in pnls:
        equity.append(equity[-1] * (1 + pnl / 100))
        peak = max(peak, equity[-1])
        mdd = max(mdd, (peak - equity[-1]) / peak * 100)

    gross_profit = float(pnls[pnls > 0].sum())
    gross_loss = float(-pnls[pnls < 0].sum())
    pf = gross_profit / gross_loss if gross_loss > 0 else (np.inf if gross_profit > 0 else np.nan)

    return {
        "trades": int(len(tdf)),
        "winrate": round(float((pnls > 0).mean() * 100), 1),
        "net": round((equity[-1] - 1) * 100, 2),
        "mdd": round(mdd, 2),
        "avg_trade": round(float(pnls.mean()), 3),
        "profit_factor": round(float(pf), 2) if np.isfinite(pf) else pf,
        "gross_profit": round(gross_profit, 2),
        "gross_loss": round(gross_loss, 2),
        "benchmark": round(float(benchmark_return), 2) if benchmark_return is not None else None,
        "details": trades,
        "equity": equity[-1]
    }


def backtest_period(df, signal_start, end_exclusive):
    """
    Backtest trades whose signal close occurs in [signal_start, end_exclusive).
    Entry is next session open. All exits must occur before end_exclusive.
    Open positions that cannot be resolved inside the period are marked censored
    and excluded from performance instead of being force-closed at a boundary.
    """
    trades = []
    censored = 0
    if df.empty or end_exclusive - signal_start < 2:
        return summarize_trades([]), censored

    in_until = signal_start - 1
    first_signal = max(39, signal_start)

    for i in range(first_signal, end_exclusive - 1):
        if i <= in_until:
            continue

        score = calculate_score(df.iloc[:i + 1])
        if score < THRESHOLD:
            continue

        entry_idx = i + 1
        if entry_idx >= end_exclusive:
            continue

        entry = float(df["Open"].iloc[entry_idx])
        if not np.isfinite(entry) or entry <= 0:
            continue

        last_allowed_exit = min(entry_idx + MAX_HOLD_SESSIONS - 1, end_exclusive - 1)
        exit_price = None
        exit_idx = None
        result = ""

        for j in range(entry_idx, last_allowed_exit + 1):
            o = float(df["Open"].iloc[j])
            h = float(df["High"].iloc[j])
            l = float(df["Low"].iloc[j])

            # A gap through the stop is filled at the open.
            if o <= entry * (1 + STOP):
                exit_price, exit_idx, result = o, j, "LOSS_GAP"
                break

            hit_target = h >= entry * (1 + TARGET)
            hit_stop = l <= entry * (1 + STOP)

            # Daily OHLC cannot reveal order; use conservative stop-first rule.
            if hit_target and hit_stop:
                exit_price, exit_idx, result = entry * (1 + STOP), j, "LOSS_BOTH_HIT"
                break
            if hit_stop:
                exit_price, exit_idx, result = entry * (1 + STOP), j, "LOSS_STOP"
                break
            if hit_target:
                exit_price, exit_idx, result = entry * (1 + TARGET), j, "WIN_TARGET"
                break

        if exit_price is None:
            # Only take a time exit if the full holding window fits inside this period.
            if entry_idx + MAX_HOLD_SESSIONS - 1 < end_exclusive:
                exit_idx = entry_idx + MAX_HOLD_SESSIONS - 1
                exit_price = float(df["Close"].iloc[exit_idx])
                result = "TIME_EXIT"
            else:
                censored += 1
                # Prevent another signal while this would-be trade remains open.
                in_until = end_exclusive - 1
                break

        pnl = trade_pnl(entry, exit_price)
        trades.append({
            "SignalDate": df.index[i].date().isoformat(),
            "EntryDate": df.index[entry_idx].date().isoformat(),
            "ExitDate": df.index[exit_idx].date().isoformat(),
            "Score": score,
            "Entry": round(entry, 2),
            "Exit": round(exit_price, 2),
            "PnL%": round(pnl, 3),
            "Result": result,
            "Win": pnl > 0
        })
        in_until = exit_idx

    # Buy-and-hold benchmark over the period, using first open and last close.
    benchmark = None
    if end_exclusive - signal_start >= 2:
        first = float(df["Open"].iloc[signal_start])
        last = float(df["Close"].iloc[end_exclusive - 1])
        if first > 0:
            benchmark = ((last / first) - 1) * 100

    return summarize_trades(trades, benchmark), censored


def split_indices(n):
    # Chronological 60/20/20 split. Holdout remains the final 20%.
    train_end = int(n * 0.60)
    validation_end = int(n * 0.80)
    return train_end, validation_end


@st.cache_data(ttl=3600, show_spinner=False)
def run_all_backtests(stock_list):
    rows = []
    details = {}
    pooled_test_trades = []
    pooled_validation_trades = []

    for ticker in stock_list:
        df = get_data(ticker, DATA_PERIOD)
        if df.empty or len(df) < 120:
            rows.append({
                "Stock": ticker, "Status": "Insufficient data", "Train trades": 0,
                "Train net %": np.nan, "Validation trades": 0, "Validation net %": np.nan,
                "Holdout trades": 0, "Holdout WR %": np.nan, "Holdout net %": np.nan,
                "Holdout PF": np.nan, "Holdout MDD %": np.nan, "Censored": 0
            })
            continue

        train_end, validation_end = split_indices(len(df))

        train, c1 = backtest_period(df, 39, train_end)
        validation, c2 = backtest_period(df, train_end, validation_end)
        holdout, c3 = backtest_period(df, validation_end, len(df))

        # Pooled trades are diagnostic only; they are not a portfolio simulation.
        for tr in validation["details"]:
            pooled_validation_trades.append({**tr, "Stock": ticker})
        for tr in holdout["details"]:
            pooled_test_trades.append({**tr, "Stock": ticker})

        details[ticker] = {
            "train": train, "validation": validation, "holdout": holdout,
            "censored": c1 + c2 + c3
        }

        rows.append({
            "Stock": ticker,
            "Status": "OK",
            "Train trades": train["trades"],
            "Train net %": train["net"],
            "Validation trades": validation["trades"],
            "Validation net %": validation["net"],
            "Holdout trades": holdout["trades"],
            "Holdout WR %": holdout["winrate"],
            "Holdout net %": holdout["net"],
            "Holdout PF": holdout["profit_factor"],
            "Holdout MDD %": holdout["mdd"],
            "Censored": c1 + c2 + c3
        })

    return pd.DataFrame(rows), details, pooled_validation_trades, pooled_test_trades


def evidence_label(trades, net, pf, mdd):
    if trades < MIN_TEST_TRADES_FOR_EVIDENCE:
        return "INSUFFICIENT EVIDENCE"
    if net is not None and net > 0 and pf is not None and np.isfinite(pf) and pf > 1 and mdd < 25:
        return "PROMISING — NEEDS FORWARD TEST"
    return "NOT PROFITABLE IN THIS HOLDOUT"


tab_live, tab_backtest, tab_method = st.tabs(
    ["LIVE TODAY", "BACKTEST & HOLDOUT", "METHODOLOGY"]
)

with tab_live:
    st.subheader("Current daily signals")
    st.caption(
        "A BUY means the rules passed using the latest downloaded daily candle. "
        "It is not a forecast probability or a guarantee of a profitable trade."
    )
    live_rows = []
    for ticker in STOCKS:
        df = get_data(ticker, "1y")
        score = calculate_score(df)
        live_rows.append({
            "Stock": ticker,
            "Score": score,
            "Signal": "BUY" if score >= THRESHOLD else "WAIT",
            "Latest data date": str(df.index[-1].date()) if not df.empty else "No data"
        })
    st.dataframe(pd.DataFrame(live_rows), use_container_width=True, hide_index=True)
    st.info(
        "Daily candles may be delayed or incomplete during the trading session. "
        "For signals based on closing prices, review after the daily candle is complete."
    )

with tab_backtest:
    st.subheader("Chronological out-of-sample evaluation")
    st.write(
        "Uses 5 years of daily data when available: first 60% training, next 20% validation, "
        "final 20% holdout. The holdout should not be used to tune thresholds."
    )
    if st.button("Run / refresh backtests", type="primary"):
        st.cache_data.clear()

    with st.spinner("Downloading data and running tests..."):
        summary, detail_map, pooled_validation, pooled_holdout = run_all_backtests(tuple(STOCKS))

    st.dataframe(summary, use_container_width=True, hide_index=True)

    # Pooled trade statistics are a diagnostic, not portfolio returns.
    st.subheader("Pooled trade diagnostics")
    st.caption(
        "These combine completed trades across stocks for diagnostic purposes only. "
        "They do not model simultaneous positions, capital allocation, or portfolio exposure."
    )
    pooled_rows = []
    for label, trades in [
        ("Validation", pooled_validation),
        ("Final holdout", pooled_holdout)
    ]:
        metrics = summarize_trades(trades)
        pooled_rows.append({
            "Period": label,
            "Trades": metrics["trades"],
            "Win rate %": metrics["winrate"],
            "Compounded trade-sequence net %": metrics["net"],
            "Average trade %": metrics["avg_trade"],
            "Profit factor": metrics["profit_factor"],
            "Max drawdown %": metrics["mdd"]
        })
    st.dataframe(pd.DataFrame(pooled_rows), use_container_width=True, hide_index=True)

    hold_metrics = summarize_trades(pooled_holdout)
    label = evidence_label(
        hold_metrics["trades"], hold_metrics["net"],
        hold_metrics["profit_factor"], hold_metrics["mdd"]
    )
    if label.startswith("PROMISING"):
        st.success(label)
    elif label.startswith("INSUFFICIENT"):
        st.warning(label)
    else:
        st.error(label)

    st.subheader("Per-stock trade details")
    available = [t for t in STOCKS if t in detail_map]
    if available:
        selected = st.selectbox("Select stock", available)
        selected_period = st.selectbox(
            "Select period", ["train", "validation", "holdout"], index=2
        )
        st.write(f"**{selected} — {selected_period.upper()}**")
        trades = detail_map[selected][selected_period]["details"]
        if trades:
            st.dataframe(pd.DataFrame(trades), use_container_width=True, hide_index=True)
        else:
            st.info("No completed trades in this period.")
        st.write(
            f"Censored / unresolved boundary trades for this stock: "
            f"{detail_map[selected]['censored']}"
        )

with tab_method:
    st.subheader("Rules and limitations")
    st.markdown(
        """
**Entry eligibility**
- At least 40 valid daily rows for indicator warm-up.
- Five-session average of `Close × Volume` at or above the configured IDR threshold.
- Latest close within 2% of the prior 20-session high.
- SMA5 above SMA20 and close above SMA20.

**Score**
- Base 50 after eligibility filters.
- +20 when the latest close is above the previous 20-session high.
- +15 when volume is at least 1.5 times its 20-session average.
- +10 when RSI is between 55 and 70 inclusive.
- −20 when RSI is above 78.
- BUY when score is at least 70.

**Execution assumptions**
- Signal calculated after a session closes; entry at next session open.
- Target +4%; stop −2%; estimated buy and sell fees applied to each trade.
- If target and stop both fall inside the same daily candle, stop is assumed first.
- A gap below the stop is filled at the opening price.
- Maximum holding period is 10 sessions, including entry day.
- Trades that cannot complete before a period boundary are censored, not forced into the result.

**What this does not prove**
- Historical profitability does not guarantee future returns.
- Daily OHLC data cannot reconstruct intraday execution order or slippage.
- `Close × Volume` is a turnover proxy; fees and market impact vary by broker and liquidity.
- Pooled trade diagnostics are not a multi-stock portfolio simulation.
- A small number of trades gives weak evidence, even if the win rate looks high.
- Test results are only genuinely out-of-sample if you do not tune the strategy using them.
        """
    )
    st.warning(
        "Before using real money, paper-trade the frozen rules prospectively and model "
        "position sizing, simultaneous signals, capital limits, taxes, slippage, and broker-specific fees."
    )
