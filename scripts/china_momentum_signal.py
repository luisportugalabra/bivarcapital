#!/usr/bin/env python3
"""
BivarChinaMomentum — Monthly Signal Generator

Loads EODHD price/fundamentals data for China A-shares (SHG + SHE),
computes 21-month momentum (skip 1 month), applies CSI 300 regime filter,
and outputs china-momentum-data.json for the website.

Strategy:
  - Signal: 21M momentum, skip 1 month
      mom = price_1M_ago / price_22M_ago - 1
  - Universe: SHG + SHE, mcap >= 20B CNY
  - Regime: CSI 300 >= MA150 → invest top 10; below → cash
  - Portfolio: top 10 equal weight, monthly rebalance
  - No fundamental filter

Usage: python3 scripts/china_momentum_signal.py
"""
import os
import json
import warnings
from datetime import datetime

import pandas as pd
import numpy as np

warnings.filterwarnings("ignore")

SCRIPT_DIR  = os.path.dirname(os.path.abspath(__file__))
SITE_DIR    = os.path.dirname(SCRIPT_DIR)
JSON_PATH    = os.path.join(SITE_DIR, "china-momentum-data.json")
HISTORY_PATH = os.path.join(SITE_DIR, "ytd-picks-history-china.json")

EODHD_DIR   = "/Users/luisabrantes/eodhd_data"
CSI300_PATH = "/Users/luisabrantes/china_momentum/csi300_daily.parquet"

EXCHANGES   = ["SHG", "SHE"]
MIN_MCAP    = 20e9          # CNY
TOP_N       = 10
TOP_DISPLAY = 30
MA_WINDOW   = 150
WINSOR_CAP  = 0.50          # ±50% monthly return cap


# ---------------------------------------------------------------------------
# 1. Regime — CSI 300 vs MA150
# ---------------------------------------------------------------------------

def check_regime():
    """Load CSI 300 daily data, compute MA150, return (last_close, ma150, is_momentum)."""
    df = pd.read_parquet(CSI300_PATH)
    df = df.sort_values("date").reset_index(drop=True)
    close = df["close"].dropna()
    if len(close) < MA_WINDOW:
        return None, None, True
    last  = float(close.iloc[-1])
    ma150 = float(close.iloc[-MA_WINDOW:].mean())
    return last, ma150, last >= ma150


# ---------------------------------------------------------------------------
# 2. Price loading — monthly resampled, winsorized
# ---------------------------------------------------------------------------

def load_monthly_prices(exchange: str) -> pd.DataFrame:
    """
    Load all adjusted_close parquet files for one exchange.
    Resample to month-end, winsorize monthly returns ±50%,
    reconstruct clean price series.
    Returns DataFrame with date index (ME) and ticker columns.
    """
    price_dir = os.path.join(EODHD_DIR, exchange, "prices")
    if not os.path.isdir(price_dir):
        return pd.DataFrame()

    frames = {}
    for fname in os.listdir(price_dir):
        if not fname.endswith(".parquet"):
            continue
        ticker = fname.replace(".parquet", "")
        fpath  = os.path.join(price_dir, fname)
        try:
            df = pd.read_parquet(fpath, columns=["adjusted_close"])
            df = df["adjusted_close"].dropna()
            if len(df) < 30:
                continue
            # Resample to month-end
            monthly = df.resample("ME").last().dropna()
            frames[ticker] = monthly
        except Exception:
            continue

    if not frames:
        return pd.DataFrame()

    combined = pd.DataFrame(frames)
    combined.index = pd.to_datetime(combined.index)

    # Winsorize: cap monthly returns at ±50%, then reconstruct prices
    ret = combined.pct_change()
    ret_clipped = ret.clip(lower=-WINSOR_CAP, upper=WINSOR_CAP)

    # Reconstruct from first available price using clipped returns
    clean = combined.copy()
    for col in combined.columns:
        s = combined[col].dropna()
        if len(s) < 2:
            continue
        r = ret_clipped[col].reindex(s.index).fillna(0)
        # Start from first actual price, then apply clipped returns forward
        prices = [s.iloc[0]]
        for rv in r.iloc[1:]:
            prices.append(prices[-1] * (1 + rv))
        clean.loc[s.index, col] = prices

    return clean


def load_all_monthly_prices() -> pd.DataFrame:
    """Load and combine monthly prices for SHG + SHE."""
    parts = []
    for exch in EXCHANGES:
        print(f"  Loading {exch} prices…")
        part = load_monthly_prices(exch)
        if not part.empty:
            # Prefix tickers with exchange to avoid duplicates
            part.columns = [f"{exch}:{c}" for c in part.columns]
            parts.append(part)

    if not parts:
        return pd.DataFrame()
    combined = pd.concat(parts, axis=1)
    combined = combined.sort_index()
    return combined


# ---------------------------------------------------------------------------
# 3. Shares outstanding — quarterly → monthly
# ---------------------------------------------------------------------------

def load_shares(exchange: str) -> pd.Series:
    """
    Load outstandingShares.quarterly from fundamentals JSONs.
    Returns Series indexed by exch:ticker with latest shares.
    """
    fund_dir = os.path.join(EODHD_DIR, exchange, "fundamentals")
    if not os.path.isdir(fund_dir):
        return pd.Series(dtype=float)

    records = {}
    for fname in os.listdir(fund_dir):
        if not fname.endswith(".json"):
            continue
        ticker = fname.replace(".json", "")
        fpath  = os.path.join(fund_dir, fname)
        try:
            with open(fpath) as f:
                d = json.load(f)
            quarterly = d.get("outstandingShares", {}).get("quarterly", {})
            if not quarterly:
                continue
            # Can be dict or list
            if isinstance(quarterly, dict):
                items = list(quarterly.values())
            else:
                items = quarterly

            # Sort by date and take the most recent
            def parse_date(item):
                return item.get("dateFormatted", item.get("date", "1900-01-01"))

            items_sorted = sorted(items, key=parse_date, reverse=True)
            latest = items_sorted[0]
            shares = latest.get("shares")
            if shares and float(shares) > 0:
                records[f"{exchange}:{ticker}"] = float(shares)
        except Exception:
            continue

    return pd.Series(records, dtype=float)


def load_all_shares() -> pd.Series:
    """Load shares outstanding for both exchanges."""
    parts = []
    for exch in EXCHANGES:
        print(f"  Loading {exch} fundamentals (shares)…")
        s = load_shares(exch)
        parts.append(s)
    return pd.concat(parts) if parts else pd.Series(dtype=float)


# ---------------------------------------------------------------------------
# 4. Company info (name + sector)
# ---------------------------------------------------------------------------

def load_company_info(exchange: str) -> pd.DataFrame:
    """Load Name and Sector from fundamentals JSONs."""
    fund_dir = os.path.join(EODHD_DIR, exchange, "fundamentals")
    if not os.path.isdir(fund_dir):
        return pd.DataFrame()

    records = []
    for fname in os.listdir(fund_dir):
        if not fname.endswith(".json"):
            continue
        ticker = fname.replace(".json", "")
        fpath  = os.path.join(fund_dir, fname)
        try:
            with open(fpath) as f:
                d = json.load(f)
            g = d.get("General", {})
            records.append({
                "key":    f"{exchange}:{ticker}",
                "ticker": ticker,
                "exchange": exchange,
                "name":   g.get("Name") or "",
                "sector": g.get("Sector") or "",
            })
        except Exception:
            continue

    return pd.DataFrame(records).set_index("key") if records else pd.DataFrame()


def load_all_company_info() -> pd.DataFrame:
    parts = []
    for exch in EXCHANGES:
        parts.append(load_company_info(exch))
    return pd.concat(parts) if parts else pd.DataFrame()


# ---------------------------------------------------------------------------
# 5. Main
# ---------------------------------------------------------------------------

def main():
    print("=" * 90)
    print("  BivarChinaMomentum — Signal Generator")
    print("=" * 90)

    # --- Regime ---
    print("\n[1/5] Checking CSI 300 regime…")
    csi300, csi300_ma150, is_momentum = check_regime()
    regime = "momentum" if is_momentum else "cash"
    print(f"  CSI 300: {csi300:,.1f}  |  MA{MA_WINDOW}: {csi300_ma150:,.1f}  |  Regime: {regime.upper()}")

    # --- Prices ---
    print("\n[2/5] Loading monthly prices (SHG + SHE)…")
    monthly_prices = load_all_monthly_prices()
    print(f"  Total tickers loaded: {monthly_prices.shape[1]}")

    # --- Shares ---
    print("\n[3/5] Loading shares outstanding…")
    shares = load_all_shares()
    print(f"  Tickers with shares data: {len(shares)}")

    # --- Company info ---
    print("\n[4/5] Loading company names and sectors…")
    info = load_all_company_info()
    print(f"  Tickers with company info: {len(info)}")

    # --- Compute signals ---
    print("\n[5/5] Computing signals…")

    # Need at least 23 monthly observations (22M lookback + current skip)
    # signal_price = iloc[-2]  (1M ago, skip last month)
    # start_price  = iloc[-23] (22M ago)
    if monthly_prices.shape[0] < 23:
        print("  ERROR: Not enough monthly history.")
        return

    signal_price_series = monthly_prices.iloc[-2]    # 1M ago
    start_price_series  = monthly_prices.iloc[-23]   # 22M ago (21M lookback + 1 skip)
    price_12m_ago       = monthly_prices.iloc[-14]   # 13M ago for 12M ret (skip 1M)

    mom_21m  = signal_price_series / start_price_series - 1
    ret_12m  = signal_price_series / price_12m_ago - 1

    # Latest price (for mcap at signal date)
    latest_price = monthly_prices.iloc[-2]  # same as signal price

    # McAP = price × shares
    mcap = latest_price * shares
    mcap = mcap.dropna()

    # Filter: mom is valid AND mcap >= 20B CNY
    valid_mask = mom_21m.notna() & (mcap >= MIN_MCAP)
    eligible_tickers = valid_mask[valid_mask].index.tolist()

    mom_valid  = mom_21m.loc[eligible_tickers]
    ret12_valid = ret_12m.reindex(eligible_tickers)
    mcap_valid  = mcap.reindex(eligible_tickers)

    # Sort by 21M momentum descending
    ranked = mom_valid.sort_values(ascending=False)
    total_eligible = len(ranked)
    print(f"  Eligible stocks (mcap >= ¥20B, 21M signal valid): {total_eligible}")

    top_keys = ranked.head(TOP_N).index.tolist()
    display_keys = ranked.head(TOP_DISPLAY).index.tolist()

    # Build top30 list
    top30 = []
    for rank, key in enumerate(display_keys, 1):
        exch, ticker = key.split(":", 1)
        row_info = info.loc[key] if key in info.index else {}
        name   = row_info["name"]   if hasattr(row_info, "__getitem__") and "name"   in row_info else ""
        sector = row_info["sector"] if hasattr(row_info, "__getitem__") and "sector" in row_info else ""

        m21  = mom_valid.get(key)
        r12  = ret12_valid.get(key)
        mc   = mcap_valid.get(key)

        entry = {
            "rank":     rank,
            "ticker":   ticker,
            "exchange": exch,
            "name":     name,
            "sector":   sector,
            "ret_21m":  round(float(m21) * 100, 1) if pd.notna(m21) else None,
            "ret_12m":  round(float(r12) * 100, 1) if pd.notna(r12) else None,
            "mcap_b":   round(float(mc) / 1e9, 1) if pd.notna(mc) else None,
            "selected": key in top_keys,
        }
        top30.append(entry)

    portfolio = [t for t in top30 if t["selected"]]

    output = {
        "date":           datetime.now().strftime("%Y-%m-%d"),
        "regime":         regime,
        "csi300":         round(csi300, 1) if csi300 else None,
        "csi300_ma150":   round(csi300_ma150, 1) if csi300_ma150 else None,
        "total_eligible": total_eligible,
        "portfolio":      portfolio,
        "top30":          top30,
    }

    with open(JSON_PATH, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\n  Saved: {JSON_PATH}")

    # --- Summary ---
    print(f"\n{'=' * 90}")
    print(f"  BivarChinaMomentum — {output['date']}")
    print(f"  CSI 300: {csi300:,.1f} | MA{MA_WINDOW}: {csi300_ma150:,.1f} | Regime: {regime.upper()}")
    print(f"  Eligible: {total_eligible} stocks")
    print(f"{'=' * 90}")
    print(f"  {'#':>3} {'':>3} {'Ticker':<10} {'Exch':<5} {'Name':<32} {'Sector':<22} {'Ret21M':>8} {'Ret12M':>8} {'MCap¥B':>8}")
    print(f"  {'-' * 90}")
    for t in top30:
        sel  = ">>>" if t["selected"] else ""
        r21  = f"{t['ret_21m']:>+7.1f}%" if t["ret_21m"] is not None else "      —"
        r12  = f"{t['ret_12m']:>+7.1f}%" if t["ret_12m"] is not None else "      —"
        mc   = f"{t['mcap_b']:>7.1f}"   if t["mcap_b"]  is not None else "      —"
        name_short = (t["name"] or "")[:31]
        sect_short = (t["sector"] or "")[:21]
        print(f"  {t['rank']:3d} {sel:>3} {t['ticker']:<10} {t['exchange']:<5} {name_short:<32} {sect_short:<22} {r21} {r12} {mc}")

    print(f"\n  >>> = Selected for portfolio (top {TOP_N})")
    print(f"  Strategy: 21M momentum (skip 1M) | >=¥20B mcap | CSI 300 < MA{MA_WINDOW} → Cash")

    # ── Update picks history ───────────────────────────────────────────────────
    _update_picks_history(top_keys, regime, output['date'])

    return output


def _update_picks_history(top_keys, regime, today_str):
    """Append new period to ytd-picks-history-china.json when a new month starts."""
    from datetime import datetime, date
    import calendar

    if not os.path.exists(HISTORY_PATH):
        print("  China picks history: file not found, skipping")
        return

    with open(HISTORY_PATH) as f:
        history = json.load(f)

    today = datetime.strptime(today_str, '%Y-%m-%d').date()
    today_ym = (today.year, today.month)

    if not history:
        print("  China picks history: empty, skipping")
        return

    last_end = datetime.strptime(history[-1]['end'], '%Y-%m-%d').date()
    last_end_ym = (last_end.year, last_end.month)

    if today_ym <= last_end_ym:
        print(f"  China picks history: already up to date ({history[-1]['end']})")
        return

    last_day = calendar.monthrange(today.year, today.month)[1]
    new_end  = date(today.year, today.month, last_day).isoformat()

    # Extract plain tickers (strip exchange prefix if present)
    tickers = [k.split(':')[-1] if ':' in k else k for k in top_keys]

    new_period = {
        'signal_date': today_str,
        'start':       history[-1]['end'],
        'end':         new_end,
        'regime':      regime,
        'tickers':     tickers if regime == 'momentum' else [],
    }
    history.append(new_period)

    with open(HISTORY_PATH, 'w') as f:
        json.dump(history, f, indent=2, ensure_ascii=False)
    print(f"  China picks history: added {new_period['start']} → {new_period['end']}  regime={regime}  tickers={tickers}")


if __name__ == "__main__":
    main()
