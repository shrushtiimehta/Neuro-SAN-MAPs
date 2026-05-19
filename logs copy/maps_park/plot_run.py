import json
import sys
from pathlib import Path
import matplotlib.pyplot as plt

REPO = Path(__file__).resolve().parents[2]
SOURCES = [
    ("logs", REPO / "logs" / "maps_park" / "run.jsonl"),
    ("logs copy", REPO / "logs copy" / "maps_park" / "run.jsonl"),
]


def load(path):
    steps, cash, park_value, cum_reward, reward, rating, shop_rev, ride_cost = (
        [], [], [], [], [], [], [], []
    )
    with path.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            if r.get("tool") != "ActionDispatcher" or "step" not in r:
                continue
            steps.append(r["step"])
            cash.append(r["cash"])
            park_value.append(r["park_value"])
            cum_reward.append(r["cumulative_reward"])
            reward.append(r["reward"])
            rating.append(r["park_rating"])
            shop_rev.append(r["shop_revenue"])
            ride_cost.append(r["ride_op_cost"])
    return {
        "steps": steps, "cash": cash, "park_value": park_value,
        "cum_reward": cum_reward, "reward": reward, "rating": rating,
        "shop_rev": shop_rev, "ride_cost": ride_cost,
    }


def plot(data, title, out):
    s = data["steps"]
    fig, axes = plt.subplots(2, 3, figsize=(15, 8))
    fig.suptitle(title, fontsize=14)

    axes[0, 0].plot(s, data["cash"], color="tab:green")
    axes[0, 0].set_title("Cash")

    axes[0, 1].plot(s, data["park_value"], color="tab:blue")
    axes[0, 1].set_title("Park Value")

    axes[0, 2].plot(s, data["cum_reward"], color="tab:purple")
    axes[0, 2].set_title("Cumulative Reward")

    axes[1, 0].plot(s, data["reward"], color="tab:orange")
    axes[1, 0].set_title("Per-step Reward")

    axes[1, 1].plot(s, data["rating"], color="tab:red")
    axes[1, 1].set_title("Park Rating")

    axes[1, 2].plot(s, data["shop_rev"], label="shop_revenue", color="tab:cyan")
    axes[1, 2].plot(s, data["ride_cost"], label="ride_op_cost", color="tab:brown")
    axes[1, 2].set_title("Shop Revenue vs Ride Op Cost")
    axes[1, 2].legend()

    for ax in axes.flat:
        ax.set_xlabel("Step")
        ax.grid(True, alpha=0.3)

    fig.tight_layout(rect=[0, 0, 1, 0.96])
    fig.savefig(out, dpi=120)
    plt.close(fig)
    print(f"wrote {out} ({len(s)} rows)")


def main():
    for label, path in SOURCES:
        if not path.exists():
            print(f"skip {label}: {path} not found", file=sys.stderr)
            continue
        data = load(path)
        out = path.parent / "run_plots.png"
        plot(data, f"Maps Park Run Telemetry — {label}", out)


if __name__ == "__main__":
    main()
