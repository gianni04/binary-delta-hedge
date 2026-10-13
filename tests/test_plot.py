import json
import math
from pathlib import Path

from reports.plot import load, plot, pnl_table


def _journal(path: Path) -> None:
    t0 = 1_760_256_000_000
    rows: list[dict[str, object]] = []
    for i in range(240):
        s = 110_000 + 400 * math.sin(i / 30)
        dpm = 0.28 + 0.05 * math.sin(i / 20)
        for name, hl in (("static", -0.28), ("dynamic", -round(dpm, 3))):
            rows.append({"type": "mark", "strategy": name, "ts_ms": t0 + i * 60_000, "S": s, "pm_mid": 0.5,
                         "sigma": 0.5, "sigma_implied": 0.5, "sigma_dvol": 0.45, "sigma_ewma": 0.4,
                         "delta_pm_btc": dpm, "hl_position": hl, "net_delta_btc": dpm + hl,
                         "pnl_total": -1.0, "pnl_pm": 0.5, "pnl_hl": -0.5, "fees_pm": 0.6, "fees_hl": 0.3,
                         "funding": 0.1})
    rows.append({"type": "fill", "strategy": "dynamic", "ts_ms": t0 + 239 * 60_000, "venue": "hyperliquid",
                 "side": "buy", "size": 0.28, "price": 110_000.0, "fee": 1.4, "maker": False, "tag": "kill_hl"})
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")


def test_plot_renders_png_and_table(tmp_path: Path) -> None:
    journal = tmp_path / "j.jsonl"
    _journal(journal)
    series, kills = load(journal)
    assert set(series) == {"static", "dynamic"} and len(kills) == 1
    out = tmp_path / "hedge.png"
    plot(series, kills, out, strike=110_000)
    assert out.stat().st_size > 50_000
    table = pnl_table(series)
    assert "| dynamic |" in table and "-1.00" in table
