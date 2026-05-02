# Data Provider Costs

## Databento

**Tier:** Stocks Starter  
**Monthly cost:** ~$29 USD  

### Coverage
- **CL.FUT** — CME front-month WTI crude oil futures
- **BZ.FUT** — ICE front-month Brent crude oil futures
- **Granularity:** 1-day, 1-hour, 1-minute OHLCV bars
- **Latency:** Real-time (no publisher delay)

### Setup
1. Create account at https://databento.com/
2. Subscribe to Stocks Starter plan
3. Add Futures dataset (CL, BZ)
4. Set `DATABENTO_API_KEY` environment variable

### API Limits
- Starter plan: generous limits for retail/algo use
- Historical data included
- No additional per-call charges within plan limits

### Integration
- Provider module: `providers/_databento.py`
- Orchestrated via `providers/pricing.py`
- Automatically used when `DATABENTO_API_KEY` is set
- Graceful fallback to yfinance on any error

---

## yfinance (Fallback)

**Cost:** Free  
**Latency:** ~15 minutes for futures  
**Coverage:** BZ=F (Brent), CL=F (WTI)  
**Status:** Fallback provider, used when Databento key is not set or Databento returns errors

---

## Twelve Data (Optional)

**Cost:** Free tier (800 calls/day, 8/min)  
**Symbols:** BRN/USD, WTI/USD  
**Key:** `TWELVEDATA_API_KEY`  
**Status:** Optional secondary provider

---

## Polygon.io (Optional)

**Cost:** Free tier available  
**Key:** `POLYGON_API_KEY`  
**Status:** Optional tertiary provider

---

*Last updated: 2026-05-02*