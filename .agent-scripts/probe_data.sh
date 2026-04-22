#!/bin/zsh
echo "FRED variants"
for s in WCESTUS1 WCRSTUS1 WCRSTUS1.csv; do
  echo "--- $s ---"
  curl -sL --max-time 8 -o /tmp/fred_probe.csv -w "  status=%{http_code} ct=%{content_type} bytes=%{size_download}\n" "https://fred.stlouisfed.org/graph/fredgraph.csv?id=$s"
  head -2 /tmp/fred_probe.csv | head -c 200
  echo
done

echo ""
echo "FRED API observations (no key)"
curl -sL --max-time 8 "https://api.stlouisfed.org/fred/series/observations?series_id=WCESTUS1&file_type=json" | head -c 500
echo

echo ""
echo "EIA v2 anon"
curl -sL --max-time 8 "https://api.eia.gov/v2/petroleum/stoc/wstk/data/?frequency=weekly&data[0]=value&length=3" | head -c 500
echo

echo ""
echo "yfinance intraday probe (python)"
python3 - <<'PY'
import yfinance as yf
try:
    h = yf.Ticker("BZ=F").history(period="2d", interval="1m")
    print("BZ=F rows=", len(h), "cols=", list(h.columns))
    print(h.tail(3))
except Exception as e:
    print("yfinance error:", repr(e))
PY
