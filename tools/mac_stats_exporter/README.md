# LEASCH Model Export

This folder is a minimal handoff package for integrating the trained LEASCH offline scheduler into another codebase such as OpenAirInterface.

It contains:

- `leasch_offline_qnet_last.pth`
  The exact offline checkpoint that was used in the testing pipeline run `OFFLINE_EVAL_LAST_LEASCH_OFFLINE_20260319T174638Z_*`.
- `model.py`
  Standalone model definition plus state-building and inference helpers.
- `example_inference.py`
  Minimal example of loading the checkpoint and running one forward pass.
- `model_manifest.json`
  Machine-readable model metadata and interface description.
- `leasch_offline_qnet_last_weights.json`
  Raw layer weights and biases exported to JSON for non-PyTorch integration.

## Model Type

- Architecture: fully connected MLP
- Input dimension: `8`
- Hidden layers: `128`, `128`
- Activations: `ReLU`
- Output dimension: `4`

The network outputs one Q-value per UE.

## Input Contract

The model assumes exactly `4` candidate UEs. The input vector is always:

`[state_0, state_1, state_2, state_3, state_4, state_5, state_6, state_7]`

with the following meaning:

1. `state_0` = `d_hat_ue0`
2. `state_1` = `d_hat_ue1`
3. `state_2` = `d_hat_ue2`
4. `state_3` = `d_hat_ue3`
5. `state_4` = normalized fairness for `ue0`
6. `state_5` = normalized fairness for `ue1`
7. `state_6` = normalized fairness for `ue2`
8. `state_7` = normalized fairness for `ue3`

### Data-rate part `d_hat`

For each UE:

- start from reported `CQI` in `[0, 15]`
- map `CQI -> spectral efficiency` using this fixed lookup table:

```text
[0.1523, 0.2344, 0.3770, 0.6016, 0.8770, 1.1758, 1.4766, 1.9141,
 2.4063, 2.7305, 3.3223, 3.9023, 4.5234, 5.1152, 5.5547, 5.8906]
```

- normalize by the fixed global maximum `5.8906`
- multiply by eligibility `g_u`:

`d_hat_u = (CQI_TO_SE[cqi_u] / 5.8906) * eligibility_u`

Eligibility is binary:

- `0` = UE is not schedulable / no data
- `1` = UE is schedulable

So if a UE is not eligible, its first-half state feature is forced to `0`.

### Fairness part

The second half of the state is a normalized fairness-memory vector derived from raw counters:

- raw fairness starts at `[0, 0, 0, 0]`
- after a scheduling decision, the selected UE fairness counter is incremented by `1`
- normalized fairness is:
  - all zeros if `max(f_raw) == 0`
  - otherwise `f_raw / max(f_raw)`

This means each fairness feature is always in `[0, 1]`.

## Output Contract

The output is a length-4 vector of Q-values:

- `output[0]` -> score for scheduling `UE 0`
- `output[1]` -> score for scheduling `UE 1`
- `output[2]` -> score for scheduling `UE 2`
- `output[3]` -> score for scheduling `UE 3`

Scheduling action:

- choose `argmax(output)`
- that index is the selected UE

There is no softmax. These are raw Q-values, not probabilities.

## Important Assumptions

- Fixed number of UEs: exactly `4`
- This checkpoint comes from the standalone offline LEASCH-style trainer, not from the Nokia simulator-coupled trainer
- The state uses CQI-derived rates from the fixed lookup table above, not hidden exact channel spectral efficiency
- The fairness vector is part of the input contract and must be maintained by the caller between scheduling decisions
- The exported model only decides which one of the 4 UEs to schedule next

## Minimal PyTorch Example

```powershell
python Codex/export/example_inference.py
```

Expected flow:

1. Build the 8D state from `cqi`, `eligibility`, and `fairness_raw`
2. Load `leasch_offline_qnet_last.pth`
3. Run one forward pass
4. Select `argmax(q_values)` as the scheduling decision

## Minimal Integration Logic

At each scheduling decision:

1. collect `CQI[4]`
2. collect `eligibility[4]`
3. keep `fairness_raw[4]` in scheduler state
4. build the 8D input vector exactly as documented here
5. run the MLP
6. select the UE with the largest Q-value
7. update fairness for the selected UE

## Source Run

- training run id: `LEASCH_OFFLINE_20260319T174638Z`
- exported checkpoint: `last`
- test run that consumed this checkpoint: `OFFLINE_EVAL_LAST_LEASCH_OFFLINE_20260319T174638Z_*`
