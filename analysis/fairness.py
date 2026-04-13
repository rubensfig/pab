 
#!/usr/bin/env python3
"""
Fairness Calculator for HQoS Systems
Calculates Jain's Fairness Index and Max-Min Fairness for loss and RX rates
"""

import pandas as pd
import numpy as np
from pathlib import Path
import json
import sys
from typing import Dict, Tuple, List

class FairnessCalculator:
    """Calculate fairness metrics for aggregated statistics"""

    def __init__(self, total_users: int = 1000):
        """
        Initialize fairness calculator

        Args:
            total_users: Total number of users in the system (for max-min fairness)
        """
        self.total_users = total_users

    @staticmethod
    def jain_fairness_index(values: np.ndarray) -> float:
        """
        Calculate Jain's Fairness Index
        J(x) = (sum(x_i))^2 / (n * sum(x_i^2))

        Args:
            values: Array of metric values

        Returns:
            JFI value between 0 and 1
        """
        values = np.array(values, dtype=float)
        n = len(values)
        sum_x = np.sum(values)
        sum_x2 = np.sum(values**2)

        if sum_x2 == 0:
            return 0.0

        jfi = (sum_x**2) / (n * sum_x2)
        return float(jfi)

    @staticmethod
    def jain_per_user_from_group_constants(values_by_group, users_by_group) -> float:
        """
        Per-user Jain fairness when each user in a group shares the same value x_g.

        J = ( (sum_g n_g x_g)^2 ) / ( (sum_g n_g) * (sum_g n_g x_g^2) )
        """
        groups = [g for g in values_by_group.keys() if g in users_by_group]
        n_total = sum(users_by_group[g] for g in groups)
        if n_total == 0:
            return 0.0

        s1 = sum(users_by_group[g] * values_by_group[g] for g in groups)
        s2 = sum(users_by_group[g] * (values_by_group[g] ** 2) for g in groups)
        if s2 == 0:
            return 0.0

        return (s1 ** 2) / (n_total * s2)

    @staticmethod
    def calculate_loss_rate(tx_frames: int, rx_frames: int) -> float:
        """
        Calculate loss rate as percentage

        Args:
            tx_frames: Transmitted frames
            rx_frames: Received frames

        Returns:
            Loss rate as percentage
        """
        if tx_frames == 0:
            return 0.0
        loss = ((tx_frames - rx_frames) / tx_frames) * 100
        return float(max(0, loss))  # Ensure non-negative

    def calculate_max_min_fairness(
        self,
        loss_rates: Dict[str, float],
        rx_rates: Dict[str, float],
        tx_rates: Dict[str, float],
        num_users: Dict[str, int]
    ) -> Dict:
        """
        Calculate max-min fairness metrics

        Max-min fairness: Users within fair share lose 0%, users exceeding lose only excess

        Args:
            loss_rates: Loss rate per flow group (%)
            rx_rates: RX rate per flow group (bps)
            tx_rates: TX rate per flow group (bps)
            num_users: Number of users per flow group

        Returns:
            Dictionary with max-min fairness metrics
        """
        # Calculate total capacity from RX rates
        total_rx = sum(rx_rates.values())
        total_tx = sum(tx_rates.values())

        # Fair share per user
        fair_share_per_user = total_rx / self.total_users

        results = {
            'fair_share_per_user_bps': fair_share_per_user,
            'groups': {}
        }

        for group_name in loss_rates.keys():
            tx_per_user = tx_rates[group_name] / num_users[group_name]
            rx_per_user = rx_rates[group_name] / num_users[group_name]
            loss_per_user_bps = tx_per_user * (loss_rates[group_name] / 100)

            # Is this group within fair share?
            within_fair_share = tx_per_user <= fair_share_per_user
            excess = max(0, tx_per_user - fair_share_per_user)
            ideal_loss_per_user = excess  # Should lose only excess
            actual_loss_per_user = loss_per_user_bps

            results['groups'][group_name] = {
                'num_users': num_users[group_name],
                'tx_per_user_bps': tx_per_user,
                'rx_per_user_bps': rx_per_user,
                'loss_per_user_bps': loss_per_user_bps,
                'loss_rate_pct': loss_rates[group_name],
                'within_fair_share': within_fair_share,
                'excess_bps': excess,
                'ideal_loss_per_user_bps': ideal_loss_per_user,
                'deviation_from_ideal_bps': abs(actual_loss_per_user - ideal_loss_per_user)
            }

        # Calculate total deviation
        total_deviation = sum(
            results['groups'][g]['deviation_from_ideal_bps'] * num_users[g]
            for g in loss_rates.keys()
        )
        results['total_deviation_bps'] = total_deviation

        return results

    def analyze_csv(self, csv_path: str) -> Dict:
        """
        Analyze a single CSV file

        Args:
            csv_path: Path to CSV file

        Returns:
            Dictionary with fairness metrics
        """
        df = pd.read_csv(csv_path)

        # df = df[df["Experiment"] == "scheme_name"]

        # Extract flow groups and their metrics
        flow_groups = df['Flow Group'].unique()

        metrics = {
            'loss_rates': {},
            'rx_rates': {},
            'tx_rates': {},
            'num_users': {},
            'raw_data': {}
        }

        for group in flow_groups:
            group_data = df[df['Flow Group'] == group].iloc[0]

            # Extract metrics
            loss_pct = float(group_data['Loss %'])
            rx_rate = float(group_data['Rx Rate (bps)'])
            tx_rate = float(group_data['Tx Rate (bps)'])
            tx_frames = int(group_data['Tx Frames'])
            rx_frames = int(group_data['Rx Frames'])
            experiment = group_data['Experiment']

            # Determine number of users (heuristic: based on flow group naming)
            if 'lp' in group.lower():
                num_users =500
                group_key = 'LP'
            elif 'hp' in group.lower():
                num_users = 200
                group_key = 'HP'
            else:
                num_users = 1
                group_key = group

            metrics['loss_rates'][group_key] = loss_pct
            metrics['rx_rates'][group_key] = rx_rate
            metrics['tx_rates'][group_key] = tx_rate
            metrics['num_users'][group_key] = num_users

            metrics['raw_data'][group_key] = {
                'tx_frames': tx_frames,
                'rx_frames': rx_frames,
                'flow_group': group
            }

        return metrics

    def format_results(self, results: Dict, scheme_name: str = "") -> str:
        """
        Format results for display

        Args:
            results: Dictionary with fairness metrics
            scheme_name: Name of the scheme (e.g., "PAB", "PRIOPROP")

        Returns:
            Formatted string for display
        """
        output = []
        output.append("\n" + "="*90)
        if scheme_name:
            output.append(f"{scheme_name} SCHEME - FAIRNESS ANALYSIS")
        else:
            output.append("FAIRNESS ANALYSIS")
        output.append("="*90 + "\n")

        # Loss Rate Fairness
        output.append("LOSS RATE FAIRNESS (Jain's Fairness Index)")
        output.append("-" * 90)
        for group, rate in results['loss_rates'].items():
            output.append(f"  {group} loss rate: {rate:.4f}%")
        output.append(f"  JFI: {results['loss_rate_jfi']:.6f}")
        output.append(f"  Rating: {self._get_jfi_rating(results['loss_rate_jfi'])}\n")

        # RX Rate Fairness
        output.append("RX RATE FAIRNESS (Jain's Fairness Index)")
        output.append("-" * 90)
        for group, rate in results['rx_rates'].items():
            output.append(f"  {group} RX rate: {rate/1e9:.2f} Gbps")
        output.append(f"  JFI: {results['rx_rate_jfi']:.6f}")
        output.append(f"  Rating: {self._get_jfi_rating(results['rx_rate_jfi'])}\n")

        # Delivery Ratio Fairness
        output.append("DELIVERY RATIO FAIRNESS (received / offered)")
        output.append("-" * 90)
        for group, ratio in results['delivery_ratios'].items():
            output.append(f"  {group} delivery: {ratio:.2f}%")
        output.append(f"  JFI: {results['delivery_ratio_jfi']:.6f}")
        output.append(f"  Rating: {self._get_jfi_rating(results['delivery_ratio_jfi'])}\n")

        # Per-User Metrics
        output.append("PER-USER METRICS")
        output.append("-" * 90)
        for group in results['loss_rates'].keys():
            output.append(f"  {group} Users: {results['num_users'][group]}")
            output.append(f"    TX per user: {results['tx_rates'][group]/results['num_users'][group]/1e6:.2f} Mbps")
            output.append(f"    RX per user: {results['rx_per_user_bps'][group]/1e6:.2f} Mbps")
            output.append(f"    Loss per user: {results['loss_per_user_bps'][group]/1e6:.4f} Mbps")
        output.append(f"  Loss Per-User JFI: {results['loss_per_user_jfi']:.6f}")
        output.append(f"  RX Per-User JFI: {results['rx_per_user_jfi']:.6f}\n")

        # Max-Min Fairness
        output.append("MAX-MIN FAIRNESS ANALYSIS")
        output.append("-" * 90)
        mm = results['max_min_fairness']
        output.append(f"  Fair share per user: {mm['fair_share_per_user_bps']/1e6:.2f} Mbps")
        for group, data in mm['groups'].items():
            output.append(f"\n  {group} Group:")
            output.append(f"    TX per user: {data['tx_per_user_bps']/1e6:.2f} Mbps ({data['tx_per_user_bps']/mm['fair_share_per_user_bps']:.2f}× fair share)")
            output.append(f"    Within fair share: {data['within_fair_share']}")
            output.append(f"    Excess: {data['excess_bps']/1e6:.4f} Mbps/user")
            output.append(f"    Actual loss: {data['loss_per_user_bps']/1e6:.4f} Mbps/user")
            output.append(f"    Ideal loss: {data['ideal_loss_per_user_bps']/1e6:.4f} Mbps/user")
            output.append(f"    Deviation: {data['deviation_from_ideal_bps']/1e6:.4f} Mbps/user")
        output.append(f"\n  Total deviation: {mm['total_deviation_bps']/1e9:.4f} Gbps")
        output.append('')

        return "\n".join(output)

    @staticmethod
    def _get_jfi_rating(jfi: float) -> str:
        """Get rating description for JFI value"""
        if jfi > 0.99:
            return "EXCELLENT"
        elif jfi > 0.95:
            return "VERY GOOD"
        elif jfi > 0.9:
            return "GOOD"
        elif jfi > 0.8:
            return "FAIR"
        elif jfi > 0.5:
            return "POOR"
        else:
            return "VERY POOR"
def analyze_all_experiments(df: pd.DataFrame, users_by_group: Dict[str, int], calc: FairnessCalculator):
    results_by_exp = {}

    df = df.copy()

    # If Experiment column missing, treat whole file as one experiment
    if "Experiment" not in df.columns:
        df["Experiment"] = "ALL"

    # Normalize flow group strings
    df["Flow Group"] = df["Flow Group"].astype(str).str.lower()

    for exp, dfe in df.groupby("Experiment"):
        loss_rates = {}
        rx_rates = {}
        tx_rates = {}
        num_users = {}

        # Match hp/lp by substring (robust to names like "hp_group", "LP-1", etc.)
        selectors = {
            "HP": dfe["Flow Group"].str.contains("hp", na=False),
            "LP": dfe["Flow Group"].str.contains("lp", na=False),
        }

        for G, sel in selectors.items():
            rows = dfe[sel]
            if rows.empty:
                continue

            row = rows.mean(numeric_only=True)

            loss_rates[G] = float(row["Loss %"])
            rx_rates[G]   = float(row["Rx Rate (bps)"])
            tx_rates[G]   = float(row["Tx Rate (bps)"])
            num_users[G]  = int(users_by_group[G.lower()])  # users_by_group expects "hp"/"lp"

        if set(loss_rates.keys()) != {"HP", "LP"}:
            # Nothing to compute for this experiment
            # (You can comment this print out once you confirm matching works.)
            print(f"[warn] Experiment={exp}: found groups={list(loss_rates.keys())}, need both HP and LP")
            continue

        # Per-user JFI on loss% (equal-loss-rate fairness)
        per_user_loss_jfi = calc.jain_per_user_from_group_constants(loss_rates, num_users)
        per_user_rate_jfi = calc.jain_per_user_from_group_constants(rx_rates, num_users)

        # Max-min “excess only loses” deviation
        total_rx = sum(rx_rates.values())
        total_users = sum(num_users.values())
        fair_share = total_rx / total_users if total_users else 0.0

        total_deviation = 0.0
        for G in ["HP", "LP"]:
            tx_per_user = tx_rates[G] / num_users[G]
            ideal_loss_per_user = max(tx_per_user - fair_share, 0.0)
            actual_loss_per_user = (loss_rates[G] / 100.0) * tx_rates[G] / num_users[G]
            total_deviation += abs(actual_loss_per_user - ideal_loss_per_user) * num_users[G]
        mean_dev_per_user = total_deviation / total_users

        results_by_exp[str(exp)] = {
            "loss_rate_jfi_per_user": per_user_loss_jfi,
            "rx_rate_jfi_per_user": per_user_rate_jfi,
            "maxmin_total_deviation_bps": total_deviation,
            "fair_share_bps_per_user": fair_share,
            "maxmin_mean_deviation_bps_per_user": mean_dev_per_user,
        }

    return results_by_exp

def main():
    if len(sys.argv) < 2:
        print("Usage: python fairness.py <csv_file> [total_users]")
        sys.exit(1)

    csv_file = sys.argv[1]
    total_users = int(sys.argv[2]) if len(sys.argv) > 2 else 1000

    df = pd.read_csv(csv_file)

    calc = FairnessCalculator(total_users=total_users)

    # users per flow group (edit if different)
    users_by_group = {"hp": 500, "lp": 500}

    results_by_exp = analyze_all_experiments(df, users_by_group, calc)
    print("\n" + "="*90)
    print("PAB vs PRIOPROP (per-experiment)")
    print("="*90)
    print(f"{'Experiment':12s} {'Loss% JFI (per-user)':22s} {'Max-min mean dev (Mbps/user)':28s} {'Fair share (Mbps/user)':22s}")
    print("-"*90)
    for exp, r in results_by_exp.items():
        print(
            f"{exp:12s} "
            f"{r['loss_rate_jfi_per_user']:22.6f} "
            f"{r['maxmin_mean_deviation_bps_per_user']/1e6:28.6f} "
            f"{r['fair_share_bps_per_user']/1e6:22.2f}"
        )
print("="*90 + "\n")

if __name__ == "__main__":
    main()
