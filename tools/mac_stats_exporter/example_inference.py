from __future__ import annotations

from pathlib import Path

import numpy as np

from model import build_state_vector, infer_q_values, load_checkpoint, select_action


def main() -> None:
    here = Path(__file__).resolve().parent
    checkpoint_path = here / "leasch_offline_qnet_last.pth"

    # Example scheduler snapshot for 4 UEs.
    cqi = [15, 8, 5, 12]
    eligibility = [1, 1, 0, 1]
    fairness_raw = [0.0, 3.0, 1.0, 2.0]

    state = build_state_vector(cqi, eligibility, fairness_raw)
    model = load_checkpoint(checkpoint_path)
    q_values = infer_q_values(model, state)
    action = select_action(q_values)

    np.set_printoptions(precision=6, suppress=True)
    print("checkpoint:", checkpoint_path.name)
    print("cqi:", cqi)
    print("eligibility:", eligibility)
    print("fairness_raw:", fairness_raw)
    print("state_vector:", state.tolist())
    print("q_values:", q_values.tolist())
    print("selected_ue:", action)


if __name__ == "__main__":
    main()
