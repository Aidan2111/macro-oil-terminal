#!/bin/zsh

echo "A) EIA historical XLS (direct, no key)"
curl -sL --max-time 15 -o /tmp/eiaA.xls -w "  status=%{http_code} bytes=%{size_download} ct=%{content_type}\n" "https://www.eia.gov/dnav/pet/hist_xls/WCESTUS1.xls"
file /tmp/eiaA.xls 2>&1 | head -1

echo ""
echo "B) EIA historical plain CSV (alt)"
curl -sL --max-time 15 -o /tmp/eiaB.csv -w "  status=%{http_code} bytes=%{size_download} ct=%{content_type}\n" "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=pet&s=WCESTUS1&f=W"
head -c 400 /tmp/eiaB.csv
echo

echo ""
echo "C) EIA dnav hist page (to verify the ids)"
curl -sL --max-time 10 -o /dev/null -w "  page_status=%{http_code}\n" "https://www.eia.gov/dnav/pet/hist/WCESTUS1W.htm"

echo ""
echo "D) try to pull EIA via its bulk data service (old v1 endpoint)"
curl -sL --max-time 15 -o /tmp/eiaD.json -w "  status=%{http_code} bytes=%{size_download}\n" "https://api.eia.gov/series/?series_id=PET.WCESTUS1.W"
head -c 400 /tmp/eiaD.json
echo

echo ""
echo "E) EIA v2 explicit no key"
curl -sL --max-time 15 -o /tmp/eiaE.json -w "  status=%{http_code} bytes=%{size_download}\n" "https://api.eia.gov/v2/petroleum/stoc/wstk/data/?frequency=weekly&data[0]=value&length=3"
head -c 800 /tmp/eiaE.json
echo

echo ""
echo "F) DataHub crude oil stocks (community mirror)"
curl -sL --max-time 10 -o /tmp/dhF.csv -w "  status=%{http_code} bytes=%{size_download}\n" "https://datahub.io/core/natural-gas/r/weekly.csv"
head -c 200 /tmp/dhF.csv
