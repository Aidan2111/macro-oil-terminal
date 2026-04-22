import json, sys

path = sys.argv[1] if len(sys.argv) > 1 else "docs/perf/baseline.json"
d = json.load(open(path))
for k in ("cold", "warm"):
    p = d[k]
    rt = p["resource_timing"]
    print(f"=== {k} ===")
    ttfb = p["ttfb_s"]; tti = p["tti_title_s"]; tfc = p["t_first_chart_s"]
    print(f"  TTFB: {ttfb}s  TTI(title): {tti}s  T-first-chart: {tfc}s")
    print(f"  resources: {rt['count']}  transfer: {rt['total_bytes']:,} B")
    print(f"  playwright body total: {p['playwright_body_bytes']:,} B")
    print("  top 5 largest resources:")
    for r in rt["largest"][:5]:
        print(f"    {r['size']:>10,} B  {r['duration_ms']:>5} ms  {r['name']}")
