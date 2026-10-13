"""Audit du journal JSONL (records `fill` et `mark`) : frais, PnL, kill-switch.

Usage : python -m risk.audit data/journal_X.jsonl [--final]

Code de sortie 1 si un contrôle échoue. Un contrôle « en attente » (donnée
pas encore écrite, run en cours) n'est pas un échec, sauf avec --final.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from risk.fees import hl_fee, pm_fee

FEE_TOL = 1e-9
PNL_TOL = 1e-6
POS_TOL = 1e-5
KILL_LEAD_MS = 7_200_000
KILL_PREFIX = "kill_"

CONTROLS: tuple[str, ...] = (
    "1 frais recalculés par fill",
    "2 frais taker non nuls",
    "3 HL maker réservé à static_hedge",
    "4 somme des fills = dernier mark",
    "5 pnl_total = décomposition",
    "6 frais cumulés monotones",
    "7 kill: aucun fill après kill_*",
    "8 kill: premier fill >= expiry - 2 h",
    "9 kill: position à plat au dernier mark",
    "10 kill: kill_close_ms présent",
)


@dataclass(frozen=True, slots=True)
class Check:
    """Résultat d'un contrôle. ok=None signifie en attente."""

    name: str
    ok: bool | None
    detail: str


@dataclass(frozen=True, slots=True)
class StrategyStats:
    """Décomposition des coûts et activité d'une stratégie."""

    name: str
    n_fills: int
    fees_pm: float
    fees_hl: float
    premium: float
    fee_pct_premium: float | None
    n_rebal: int
    hl_notional: float


@dataclass(frozen=True, slots=True)
class AuditReport:
    """Rapport complet ; ok est faux si un contrôle a échoué."""

    journal: str
    checks: tuple[Check, ...]
    stats: tuple[StrategyStats, ...]

    @property
    def ok(self) -> bool:
        """Vrai si aucun contrôle n'a échoué (les contrôles en attente passent)."""
        return all(c.ok is not False for c in self.checks)


def load_records(path: Path) -> list[dict[str, Any]]:
    """Lit le JSONL. Une dernière ligne tronquée (écriture en cours) est ignorée."""
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    records: list[dict[str, Any]] = []
    for idx, line in enumerate(lines):
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            if idx == len(lines) - 1:
                break
            raise ValueError(f"ligne {idx + 1} : JSON invalide") from None
        if rec.get("type") not in ("fill", "mark") or "strategy" not in rec:
            raise ValueError(f"ligne {idx + 1} : record type/strategy invalide")
        records.append(rec)
    return records


def meta_path_for(journal: Path) -> Path:
    """journal_<X>.jsonl -> meta_<X>.json dans le même dossier."""
    stem = journal.name.removesuffix(".jsonl")
    tag = stem.removeprefix("journal_")
    return journal.with_name(f"meta_{tag}.json")


def read_expiry_ms(journal: Path) -> int | None:
    """Échéance lue dans le fichier meta du run, ou None s'il est absent."""
    meta = meta_path_for(journal)
    if not meta.is_file():
        return None
    data = json.loads(meta.read_text(encoding="utf-8"))
    return int(data["spec"]["expiry_ms"])


def expected_fee(rec: dict[str, Any]) -> float:
    """Frais attendus d'un fill selon risk/fees.py."""
    size = float(rec["size"])
    price = float(rec["price"])
    maker = bool(rec["maker"])
    if rec["venue"] == "polymarket":
        return pm_fee(size, price, maker)
    return hl_fee(size * price, maker)


def _fill_errors(fills: list[dict[str, Any]], errs: dict[str, list[str]]) -> None:
    """Contrôles 1, 2, 3 sur les fills d'une stratégie."""
    for f in fills:
        tag = str(f["tag"])
        venue = str(f["venue"])
        price = float(f["price"])
        fee = float(f["fee"])
        maker = bool(f["maker"])
        try:
            exp = expected_fee(f)
        except ValueError as exc:
            errs[CONTROLS[0]].append(f"{tag} {venue}: {exc}")
            continue
        if abs(fee - exp) > FEE_TOL:
            errs[CONTROLS[0]].append(f"{tag} {venue} fee={fee} attendu={exp}")
        taker_priced = venue == "hyperliquid" or 0.0 < price < 1.0
        if not maker and taker_priced and float(f["size"]) > 0 and fee == 0.0:
            errs[CONTROLS[1]].append(f"{tag} {venue} taker à frais nul")
        if venue == "hyperliquid" and maker and tag != "static_hedge":
            errs[CONTROLS[2]].append(f"maker HL tag={tag}")


def _kill_errors(
    fills: list[dict[str, Any]],
    expiry_ms: int | None,
    errs: dict[str, list[str]],
    pend: dict[str, str],
) -> bool:
    """Contrôles 7 et 8. Renvoie True si un kill_* a été exécuté."""
    kill_idx = next(
        (i for i, f in enumerate(fills) if str(f["tag"]).startswith(KILL_PREFIX)),
        None,
    )
    if kill_idx is None:
        pend[CONTROLS[7]] = "pas encore de fill kill_*"
        return False
    for f in fills[kill_idx:]:
        if not str(f["tag"]).startswith(KILL_PREFIX):
            errs[CONTROLS[6]].append(f"fill {f['tag']} après kill_*")
    if expiry_ms is None:
        pend[CONTROLS[7]] = "meta absent, échéance inconnue"
    else:
        deadline = expiry_ms - KILL_LEAD_MS
        kill_ts = int(fills[kill_idx]["ts_ms"])
        if kill_ts < deadline:
            errs[CONTROLS[7]].append(f"kill à {kill_ts} < deadline {deadline}")
    return True


def _strategy_errors(
    name: str,
    records: list[dict[str, Any]],
    expiry_ms: int | None,
    errs: dict[str, list[str]],
    pend: dict[str, str],
) -> None:
    """Applique tous les contrôles à une stratégie."""
    fills = [r for r in records if r["type"] == "fill"]
    marks = [r for r in records if r["type"] == "mark"]
    _fill_errors(fills, errs)

    if not marks:
        pend[CONTROLS[3]] = "aucun mark"
    else:
        last = marks[-1]
        for venue, key in (("polymarket", "fees_pm"), ("hyperliquid", "fees_hl")):
            total = sum(float(f["fee"]) for f in fills if f["venue"] == venue)
            if abs(total - float(last[key])) > PNL_TOL:
                errs[CONTROLS[3]].append(f"{name} {key}: fills={total} mark={last[key]}")

    prev_pm = prev_hl = 0.0
    for m in marks:
        funding = float(m.get("funding", 0.0))
        fees_pm = float(m["fees_pm"])
        fees_hl = float(m["fees_hl"])
        recomposed = (
            float(m["pnl_pm"]) + float(m["pnl_hl"]) - fees_pm - fees_hl - funding
        )
        if abs(float(m["pnl_total"]) - recomposed) > PNL_TOL:
            errs[CONTROLS[4]].append(f"{name} ts={m['ts_ms']} pnl_total incohérent")
        if fees_pm < prev_pm - PNL_TOL or fees_hl < prev_hl - PNL_TOL:
            errs[CONTROLS[5]].append(f"{name} ts={m['ts_ms']} frais décroissants")
        prev_pm, prev_hl = fees_pm, fees_hl

    has_kill = _kill_errors(fills, expiry_ms, errs, pend)
    if not has_kill:
        for c in (CONTROLS[8], CONTROLS[9]):
            pend[c] = "pas encore de fill kill_*"
        return
    if not marks:
        return
    last = marks[-1]
    if abs(float(last["hl_position"])) > POS_TOL:
        errs[CONTROLS[8]].append(f"{name} hl_position={last['hl_position']}")
    pm_net = sum(
        float(f["size"]) * (1.0 if f["side"] == "buy" else -1.0)
        for f in fills
        if f["venue"] == "polymarket"
    )
    if abs(pm_net) > PNL_TOL:
        errs[CONTROLS[8]].append(f"{name} pm_net={pm_net}")
    if "kill_close_ms" not in last:
        errs[CONTROLS[9]].append(f"{name} kill_close_ms absent du dernier mark")


def _stats(name: str, records: list[dict[str, Any]]) -> StrategyStats:
    """Frais, prime payée, rebalancements et notionnel HL d'une stratégie."""
    fills = [r for r in records if r["type"] == "fill"]
    fees_pm = sum(float(f["fee"]) for f in fills if f["venue"] == "polymarket")
    fees_hl = sum(float(f["fee"]) for f in fills if f["venue"] == "hyperliquid")
    premium = sum(
        float(f["size"]) * float(f["price"])
        for f in fills
        if f["venue"] == "polymarket" and f["tag"] == "entry_pm" and f["side"] == "buy"
    )
    pct = (fees_pm + fees_hl) / premium * 100.0 if premium > 0 else None
    return StrategyStats(
        name=name,
        n_fills=len(fills),
        fees_pm=fees_pm,
        fees_hl=fees_hl,
        premium=premium,
        fee_pct_premium=pct,
        n_rebal=sum(1 for f in fills if f["tag"] == "dyn_rebal"),
        hl_notional=sum(
            float(f["size"]) * float(f["price"]) for f in fills if f["venue"] == "hyperliquid"
        ),
    )


def audit(journal_path: str | Path, final: bool = False) -> AuditReport:
    """Audite un journal JSONL. Avec final=True, les contrôles en attente échouent."""
    path = Path(journal_path)
    records = load_records(path)
    expiry_ms = read_expiry_ms(path)
    names: list[str] = list(dict.fromkeys(str(r["strategy"]) for r in records))

    errs: dict[str, list[str]] = {c: [] for c in CONTROLS}
    pend: dict[str, str] = {}
    stats: list[StrategyStats] = []
    for name in names:
        recs = [r for r in records if r["strategy"] == name]
        _strategy_errors(name, recs, expiry_ms, errs, pend)
        stats.append(_stats(name, recs))

    checks: list[Check] = []
    for control in CONTROLS:
        if errs[control]:
            checks.append(Check(control, False, "; ".join(errs[control][:3])))
        elif control in pend:
            ok: bool | None = False if final else None
            checks.append(Check(control, ok, f"en attente : {pend[control]}"))
        else:
            checks.append(Check(control, True, "ok"))
    return AuditReport(str(path), tuple(checks), tuple(stats))


def render(report: AuditReport) -> str:
    """Rapport texte lisible."""
    lines = [f"Journal : {report.journal}", "", "Contrôles :"]
    for c in report.checks:
        mark = {True: "OK     ", False: "ECHEC  ", None: "ATTENTE"}[c.ok]
        lines.append(f"  [{mark}] {c.name} : {c.detail}")
    lines.append("")
    lines.append("Décomposition par stratégie :")
    for s in report.stats:
        pct = f"{s.fee_pct_premium:.3f} %" if s.fee_pct_premium is not None else "n/a"
        lines.append(
            f"  {s.name} : fills={s.n_fills} frais_pm={s.fees_pm:.5f} $ "
            f"frais_hl={s.fees_hl:.5f} $ prime={s.premium:.2f} $ frais/prime={pct} "
            f"rebal_dyn={s.n_rebal} notionnel_hl={s.hl_notional:.2f} $"
        )
    lines.append("")
    lines.append("RÉSULTAT : " + ("OK" if report.ok else "ECHEC"))
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> int:
    """Point d'entrée CLI : renvoie 1 si un contrôle échoue."""
    parser = argparse.ArgumentParser(description="Audit d'un journal JSONL.")
    parser.add_argument("journal", help="chemin du journal_*.jsonl")
    parser.add_argument("--final", action="store_true", help="contrôles en attente = échec")
    args = parser.parse_args(argv)
    report = audit(args.journal, final=args.final)
    sys.stdout.buffer.write((render(report) + "\n").encode("utf-8"))
    return 0 if report.ok else 1


if __name__ == "__main__":
    sys.exit(main())
