from __future__ import annotations

"""Standalone LEASCH offline model wrapper for OAI handoff.

This file is intentionally self-contained. It exposes:
- the exact 4-UE / 8-feature model architecture
- the CQI->SE lookup used to build the state
- the state-building contract
- simple checkpoint loading and inference helpers
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F


# CQI -> spectral efficiency table used by the exported offline LEASCH model.
CQI_TO_SE = np.array(
    [
        0.1523,
        0.2344,
        0.3770,
        0.6016,
        0.8770,
        1.1758,
        1.4766,
        1.9141,
        2.4063,
        2.7305,
        3.3223,
        3.9023,
        4.5234,
        5.1152,
        5.5547,
        5.8906,
    ],
    dtype=np.float32,
)

NUM_UES = 4
STATE_DIM = 8
ACTION_DIM = 4
MAX_SE = float(CQI_TO_SE.max())


@dataclass(frozen=True)
class ModelInterface:
    num_ues: int = NUM_UES
    state_dim: int = STATE_DIM
    action_dim: int = ACTION_DIM
    hidden_dim: int = 128
    max_se: float = MAX_SE


class LeaschOfflineQNet(nn.Module):
    """Exact exported network: 8 -> 128 -> 128 -> 4 with ReLU."""

    def __init__(self) -> None:
        super().__init__()
        self.fc1 = nn.Linear(STATE_DIM, 128)
        self.fc2 = nn.Linear(128, 128)
        self.fc3 = nn.Linear(128, ACTION_DIM)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.fc3(F.relu(self.fc2(F.relu(self.fc1(x)))))


def cqi_to_normalized_data_rate(cqi: Sequence[int]) -> np.ndarray:
    """Map 4 CQI integers into 4 normalized data-rate features in [0, 1]."""

    cqi_array = np.asarray(cqi, dtype=np.int64)
    if cqi_array.shape != (NUM_UES,):
        raise ValueError(f"Expected {NUM_UES} CQI values, got shape {cqi_array.shape}.")
    if np.any(cqi_array < 0) or np.any(cqi_array > 15):
        raise ValueError("CQI values must be integers in [0, 15].")
    return (CQI_TO_SE[cqi_array] / MAX_SE).astype(np.float32)


def normalize_fairness(fairness_raw: Sequence[float]) -> np.ndarray:
    """Normalize fairness counters by their current maximum.

    If all raw fairness values are zero, the normalized fairness vector is all zeros.
    """

    fairness = np.asarray(fairness_raw, dtype=np.float32)
    if fairness.shape != (NUM_UES,):
        raise ValueError(
            f"Expected {NUM_UES} fairness values, got shape {fairness.shape}."
        )
    max_value = float(np.max(fairness))
    if max_value <= 0.0:
        return np.zeros(NUM_UES, dtype=np.float32)
    return (fairness / max_value).astype(np.float32)


def build_state_vector(
    cqi: Sequence[int],
    eligibility: Sequence[int],
    fairness_raw: Sequence[float],
) -> np.ndarray:
    """Build the exact 8D state vector consumed by the exported model.

    State layout:
    - state[0:4] = d_hat_u = normalized_data_rate_u * eligibility_u
    - state[4:8] = normalized fairness vector
    """

    eligibility_array = np.asarray(eligibility, dtype=np.float32)
    if eligibility_array.shape != (NUM_UES,):
        raise ValueError(
            f"Expected {NUM_UES} eligibility values, got shape {eligibility_array.shape}."
        )
    if np.any((eligibility_array != 0) & (eligibility_array != 1)):
        raise ValueError("Eligibility values must be binary 0/1.")

    data_rate = cqi_to_normalized_data_rate(cqi)
    fairness_norm = normalize_fairness(fairness_raw)
    d_hat = (data_rate * eligibility_array).astype(np.float32)
    return np.concatenate([d_hat, fairness_norm]).astype(np.float32)


def load_checkpoint(checkpoint_path: str | Path, device: str = "cpu") -> LeaschOfflineQNet:
    """Load the exported offline checkpoint into the standalone model class."""

    checkpoint = torch.load(Path(checkpoint_path), map_location=device)
    model = LeaschOfflineQNet().to(device)
    model.load_state_dict(checkpoint["model_state_dict"])
    model.eval()
    return model


def infer_q_values(
    model: LeaschOfflineQNet,
    state_vector: Sequence[float],
    device: str = "cpu",
) -> np.ndarray:
    """Run one forward pass and return 4 Q-values ordered by UE index."""

    state = np.asarray(state_vector, dtype=np.float32)
    if state.shape != (STATE_DIM,):
        raise ValueError(f"Expected state shape {(STATE_DIM,)}, got {state.shape}.")
    with torch.no_grad():
        tensor = torch.tensor(state, dtype=torch.float32, device=device).unsqueeze(0)
        q_values = model(tensor).squeeze(0).cpu().numpy().astype(np.float32)
    return q_values


def select_action(q_values: Sequence[float]) -> int:
    """Select the scheduling action as argmax over the 4 Q-values."""

    q = np.asarray(q_values, dtype=np.float32)
    if q.shape != (ACTION_DIM,):
        raise ValueError(f"Expected {ACTION_DIM} Q-values, got shape {q.shape}.")
    return int(np.argmax(q))
