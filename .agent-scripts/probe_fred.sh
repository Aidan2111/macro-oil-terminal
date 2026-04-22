#!/bin/zsh

echo "A) WCRSTUS1 with cosd param"
curl -sL --max-time 12 -o /tmp/fredA.csv -w "  status=%{http_code} bytes=%{size_download} ct=%{content_type}\n" "https://fred.stlouisfed.org/graph/fredgraph.csv?id=WCRSTUS1&cosd=2018-01-01"
head -3 /tmp/fredA.csv

echo ""
echo "B) WCESTUS1 with cosd param"
curl -sL --max-time 12 -o /tmp/fredB.csv -w "  status=%{http_code} bytes=%{size_download} ct=%{content_type}\n" "https://fred.stlouisfed.org/graph/fredgraph.csv?id=WCESTUS1&cosd=2018-01-01"
head -3 /tmp/fredB.csv

echo ""
echo "C) WCESTUS1 with UA"
curl -sL --max-time 12 -H 'User-Agent: Mozilla/5.0 (Macintosh) AppleWebKit/605' -o /tmp/fredC.csv -w "  status=%{http_code} bytes=%{size_download} ct=%{content_type}\n" "https://fred.stlouisfed.org/graph/fredgraph.csv?id=WCESTUS1&cosd=2018-01-01"
head -3 /tmp/fredC.csv

echo ""
echo "D) WCRSTUS1 no params"
curl -sL --max-time 12 -H 'User-Agent: Mozilla/5.0' -o /tmp/fredD.csv -w "  status=%{http_code} bytes=%{size_download} ct=%{content_type}\n" "https://fred.stlouisfed.org/graph/fredgraph.csv?id=WCRSTUS1"
head -3 /tmp/fredD.csv

echo ""
echo "E) FRED series/observations JSON (no key) — will 400 without key, but confirms API"
curl -sL --max-time 10 "https://api.stlouisfed.org/fred/series/observations?series_id=WCRSTUS1&file_type=json&limit=3" | head -c 300
echo
