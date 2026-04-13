#!/usr/bin/env python3
"""
Compute fairness metrics (JFI + demand-based max–min deviation) from RAW fairness.csv.

Groups:
- G1..G4 (or lp1..lp4 in labels)
- Defaults match the paper table:
    G1: 50 users
    G2: 150 users
    G3: 300 users
    G4: 500 users

Metrics:
1) Jain’s fairness index (JFI) over per-user Rx rates (weighted by group size) ↑

2) Max–min fairness as min–max deviation, where the *ideal* is computed using
   TOTAL OFFERED LOAD as capacity:
      C = sum_g Tx_g
   but deviation is normalized by TOTAL RX (as requested):
      max_g |Rx_g - Rx*_g| / sum_g Rx_g

Interpretation:
- Rx*_g is the demand-aware max–min fair target based on offered load (Tx) and per-user demands.
- This matches the classical intuition: satisfy low-demand groups first, then share remaining capacity.

Writes:
- fairness_basic_per_run.csv
- fairness_basic_by_experiment.csv
"""

from __future__ import annotations

import argparse
import math
import re
import pandas as pd


def jain_weighted_group_constants(value_by_group: dict[str, float], users_by_group: dict[str, int]) -> float:
    s1 = sum(users_by_group[g] * value_by_group[g] for g in value_by_group)
    s2 = sum(users_by_group[g] * (value_by_group[g] ** 2) for g in value_by_group)
    n = sum(users_by_group[g] for g in value_by_group)
    if n <= 0 or s2 <= 0:
        return 0.0
    return (s1 ** 2) / (n * s2)


def group_from_flow_group(s: str) -> str | None:
    """Extract group id 1..4 from Flow Group string: accepts g1..g4, group1..4, or lp1..lp4."""
    s = str(s).lower()
    m = re.search(r"\bg\s*([1-4])\b", s) or re.search(r"group\s*([1-4])", s)
    if not m:
        m = re.search(r"\blp\s*([1-4])\b", s) or re.search(r"lp([1-4])", s)
    if not m:
        return None
    return f"G{m.group(1)}"


def maxmin_waterfill(per_user_demands: dict[str, float], users: dict[str, int], capacity_total: float) -> dict[str, float]:
    """
    Max–min fair per-user allocation with per-user caps (demands), via water-filling.

    Find r such that sum_g users[g] * min(demand_g, r) = capacity_total
    Allocation per user: a_g = min(demand_g, r)
    """
    if capacity_total <= 0:
        return {g: 0.0 for g in per_user_demands}

    max_demand = max((max(per_user_demands[g], 0.0) for g in per_user_demands), default=0.0)
    if max_demand <= 0:
        return {g: 0.0 for g in per_user_demands}

    def total_at(r: float) -> float:
        return sum(users[g] * min(max(per_user_demands[g], 0.0), r) for g in per_user_demands)

    # If capacity >= total demand, everyone gets demand
    if capacity_total >= total_at(max_demand):
        return {g: max(per_user_demands[g], 0.0) for g in per_user_demands}

    lo, hi = 0.0, max_demand
    for _ in range(80):
        mid = (lo + hi) / 2.0
        if total_at(mid) >= capacity_total:
            hi = mid
        else:
            lo = mid

    r = hi
    return {g: min(max(per_user_demands[g], 0.0), r) for g in per_user_demands}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="Path to RAW fairness.csv")

    # Defaults match your paper table
    ap.add_argument("--users-g1", type=int, default=50)
    ap.add_argument("--users-g2", type=int, default=150)
    ap.add_argument("--users-g3", type=int, default=300)
    ap.add_argument("--users-g4", type=int, default=500)

    ap.add_argument("--tx-col", default="Tx Rate (bps)", help="Column name for Tx rate (bps)")
    ap.add_argument("--rx-col", default="Rx Rate (bps)", help="Column name for Rx rate (bps)")
    ap.add_argument("--flow-col", default="Flow Group", help="Column name for flow group label")
    ap.add_argument("--exp-col", default="Experiment", help="Column name for experiment/scheduler")
    ap.add_argument("--repeat-col", default="Repeat", help="Column name for repeat id")
    ap.add_argument("--instance-col", default="Instance", help="Column name for instance id")
    ap.add_argument("--overload", type=float, default=1.5,
                help="Overload factor: offered = overload * capacity (default: 1.5)")
    args = ap.parse_args()

    group_names = ["G1", "G2", "G3", "G4"]
    users = {"G1": args.users_g1, "G2": args.users_g2, "G3": args.users_g3, "G4": args.users_g4}

    df = pd.read_csv(args.csv)

    required = {args.flow_col, args.tx_col, args.rx_col, args.exp_col, args.repeat_col, args.instance_col}
    missing = required - set(df.columns)
    if missing:
        raise SystemExit(f"CSV missing columns: {sorted(missing)}")

    df["Group"] = df[args.flow_col].apply(group_from_flow_group)
    df = df[df["Group"].isin(group_names)].copy()

    df[args.tx_col] = pd.to_numeric(df[args.tx_col], errors="coerce")
    df[args.rx_col] = pd.to_numeric(df[args.rx_col], errors="coerce")

    run_rows = []

    for (exp, rep, inst), dfr in df.groupby([args.exp_col, args.repeat_col, args.instance_col], dropna=False):
        rec = {}
        for _, r in dfr.iterrows():
            g = r["Group"]
            tx_bps = float(r[args.tx_col]) if pd.notna(r[args.tx_col]) else math.nan
            rx_bps = float(r[args.rx_col]) if pd.notna(r[args.rx_col]) else math.nan
            rec[g] = {"tx_bps": tx_bps, "rx_bps": rx_bps}

        if set(rec.keys()) != set(group_names):
            continue

        rx_per_user = {g: rec[g]["rx_bps"] / users[g] for g in group_names}
        tx_per_user = {g: rec[g]["tx_bps"] / users[g] for g in group_names}

        # 1) JFI on per-user Rx
        jfi = jain_weighted_group_constants(rx_per_user, users)

        # 2) Demand-based max–min ideal uses scheduler-independent capacity inferred from overload
        total_tx = sum(rec[g]["tx_bps"] for g in group_names)  # offered load
        capacity_ideal = (total_tx / args.overload) if args.overload > 0 else total_tx

        ideal_per_user = maxmin_waterfill(tx_per_user, users, capacity_ideal)
        ideal_group_rx = {g: ideal_per_user[g] * users[g] for g in group_names}

        # deviation normalized by TOTAL RX (per your requirement)
        total_rx = sum(rec[g]["rx_bps"] for g in group_names)
        dev_group = {g: abs(rec[g]["rx_bps"] - ideal_group_rx[g]) for g in group_names}
        minmax_dev_norm_by_rx = (max(dev_group.values()) / total_rx) if total_rx > 0 else 0.0

        run_rows.append(
            {
                "Experiment": str(exp),
                "Repeat": rep,
                "Instance": inst,
                "JFI (Rx/user) ↑": jfi,
                "Min–max deviation (ideal uses total Tx; norm by total Rx) ↓": minmax_dev_norm_by_rx,
                "Total Tx (Gbps)": total_tx / 1e9,
                "Total Rx (Gbps)": total_rx / 1e9,
            }
        )

    out_run = pd.DataFrame(run_rows).sort_values(["Experiment", "Instance", "Repeat"])
    pd.set_option("display.float_format", lambda x: f"{x:.6f}")

    print("\nFairness metrics (per run)")
    if out_run.empty:
        print("No complete runs found (expected 4 groups G1..G4 per Experiment/Repeat/Instance).")
    else:
        print(out_run.to_string(index=False))

    out_run.to_csv("fairness_basic_per_run.csv", index=False)

    if not out_run.empty:
        agg = (
            out_run.groupby("Experiment", as_index=False)
            .agg(
                **{
                    "JFI mean": ("JFI (Rx/user) ↑", "mean"),
                    "JFI std": ("JFI (Rx/user) ↑", "std"),
                    "Min–max dev mean": ("Min–max deviation (ideal uses total Tx; norm by total Rx) ↓", "mean"),
                    "Min–max dev std": ("Min–max deviation (ideal uses total Tx; norm by total Rx) ↓", "std"),
                    "Total Tx mean (Gbps)": ("Total Tx (Gbps)", "mean"),
                    "Total Rx mean (Gbps)": ("Total Rx (Gbps)", "mean"),
                    "n runs": ("Total Rx (Gbps)", "count"),
                }
            )
            .sort_values("Experiment")
        )

        print("\nFairness metrics (aggregated by Experiment)")
        print(agg.to_string(index=False))
        agg.to_csv("fairness_basic_by_experiment.csv", index=False)

    print("\nWrote:")
    print(" - fairness_basic_per_run.csv")
    if not out_run.empty:
        print(" - fairness_basic_by_experiment.csv")


if __name__ == "__main__":
    main()
