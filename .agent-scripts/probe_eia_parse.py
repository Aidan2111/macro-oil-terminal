"""Parse EIA dnav LeafHandler HTML into a DataFrame."""
import re
import sys
import pandas as pd
import requests

# Series: WCESTUS1 = weekly US ending stocks excluding SPR of crude oil
# WCSSTUS1 = weekly US SPR stocks. Values in thousand barrels.
URL_CMCL = "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=pet&s=WCESTUS1&f=W"
URL_SPR = "https://www.eia.gov/dnav/pet/hist/LeafHandler.ashx?n=pet&s=WCSSTUS1&f=W"


def fetch(url: str) -> pd.Series:
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    html = r.text
    # The dnav pages render a wide HTML table with columns Year | Jan | ... | Dec or
    # a week-oriented table. The "Decade" table is easier: extract YYYY-MM-DD / value
    # pairs from <td> rows.
    # Simpler: EIA exposes an "annual data table" where each <tr> has a date link and
    # a numeric cell. Extract by regex.
    # Lines look like: <td class="B3">1982-08-20</td>...<td align="right">337,965</td>
    # But often the tables are keyed by year with columns per week number. We'll try
    # a resilient approach: collect all date-like cells and sibling numeric cells.
    rows = re.findall(
        r'(\d{4}-\d{2}-\d{2}).*?<td[^>]*>\s*([0-9,]+)\s*</td>',
        html, flags=re.S,
    )
    if not rows:
        # Fallback: year-week table; columns look like W1...W52 per year
        # Parse <tr> by <tr>; first cell is year, subsequent numeric cells correspond
        # to weeks. Map via td.B3 / td.B6 alternation.
        year_blocks = re.findall(r'<tr[^>]*>(.*?)</tr>', html, flags=re.S)
        collected = []
        for block in year_blocks:
            year_match = re.search(r'<td[^>]*>\s*(\d{4})\s*</td>', block)
            if not year_match:
                continue
            year = int(year_match.group(1))
            vals = re.findall(r'<td[^>]*>\s*([0-9,]+|-)\s*</td>', block)
            # First cell is year, rest are weekly values
            for week_idx, v in enumerate(vals[1:], start=1):
                if v in ("-",):
                    continue
                try:
                    num = int(v.replace(",", ""))
                except ValueError:
                    continue
                # Approximate: Friday of ISO week N
                try:
                    date = pd.Timestamp.fromisocalendar(year, min(week_idx, 52), 5)
                    collected.append((date, num))
                except Exception:
                    pass
        rows = collected

    if not rows:
        raise RuntimeError("could not parse EIA LeafHandler HTML")

    dates = []
    values = []
    for row in rows:
        if isinstance(row, tuple) and len(row) == 2:
            d, v = row
            if isinstance(v, str):
                v = int(v.replace(",", ""))
            dates.append(pd.Timestamp(d))
            values.append(v)
    s = pd.Series(values, index=pd.DatetimeIndex(dates)).sort_index()
    return s


if __name__ == "__main__":
    c = fetch(URL_CMCL)
    print(f"commercial rows={len(c)} first={c.index.min()} last={c.index.max()}")
    print(c.tail(8))
    try:
        s = fetch(URL_SPR)
        print(f"SPR rows={len(s)} first={s.index.min()} last={s.index.max()}")
        print(s.tail(8))
    except Exception as e:
        print(f"SPR parse failed: {e}")
