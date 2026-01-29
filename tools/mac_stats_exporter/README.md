# OAI MAC Stats Exporter

This small exporter reads `nrMAC_stats.log` and exposes key metrics (CQI, SNR, BLER, TX/RX bytes, throughput) for Prometheus/Grafana.

## What you get

Metrics exposed at `/metrics`:
- `oai_mac_cqi{rnti}`
- `oai_mac_ri{rnti}`
- `oai_mac_snr_db{rnti}`
- `oai_mac_dl_bler{rnti}` / `oai_mac_ul_bler{rnti}`
- `oai_mac_tx_bytes{rnti}` / `oai_mac_rx_bytes{rnti}`
- `oai_mac_tx_bps{rnti}` / `oai_mac_rx_bps{rnti}`

Note: CQI/RI appears only if the gNB prints CSI reports in `nrMAC_stats.log`.

## Put the files on your Google Cloud VM (beginner friendly)

You have two easy options:

### Option A: Use WinSCP (Windows GUI)
1. Open **WinSCP** and connect to your VM using SSH (same host/user/port you use in PuTTY/terminal).
2. Navigate on the VM side to your repo, e.g.:
   `/home/<your-user>/openairinterface5g`
3. On your local machine, open the folder that contains `tools/mac_stats_exporter/`.
4. Drag the **entire folder** `mac_stats_exporter` into:
   `/home/<your-user>/openairinterface5g/tools/`

This is safe; you’re just copying files into the repo folder.

### Option B: Use `scp` (command line)
From your Windows terminal (PowerShell) or Linux terminal:
```bash
scp -r tools/mac_stats_exporter <your-user>@<VM-IP>:/home/<your-user>/openairinterface5g/tools/
```

If your repo is in a different path, replace it accordingly.

## Run exporter (same host as gNB)

From the repo root:
```bash
./tools/mac_stats_exporter/mac_stats_exporter.py --log /path/to/nrMAC_stats.log --port 9109
```

The gNB writes `nrMAC_stats.log` in the directory where you started `nr-softmodem`.

## Run Prometheus + Grafana (optional)

From `tools/mac_stats_exporter`:
```bash
docker compose up -d
```

### How do I open Grafana if I only have SSH (no browser)?

Use an **SSH tunnel** so you can open the UI in your local browser.

From your **local laptop** (not inside the VM):
```bash
ssh -L 3000:localhost:3000 -L 9090:localhost:9090 <your-user>@<VM-IP>
```

Then open these URLs **on your local laptop browser**:
- Grafana: http://localhost:3000  (user `admin`, pass `admin`)
- Prometheus: http://localhost:9090

You will see the graphs in your **local browser**, even though everything runs on the VM.

If this does not work, make sure:
1. You used the SSH tunnel command above.
2. Docker containers are running: `docker compose ps`

### If you prefer to open via public IP (not recommended)
You can also expose the ports directly and open:
```
http://<VM-IP>:3000
http://<VM-IP>:9090
```
But for this you must open firewall rules in Google Cloud (and it’s less secure).

Open Grafana at: http://localhost:3000 (user `admin`, pass `admin`).

Prometheus is at http://<VM-IP>:9090.

### Quick Grafana panels

Create a panel and use these PromQL examples:

- CQI: `oai_mac_cqi`
- Downlink throughput (bps): `oai_mac_tx_bps`
- Uplink throughput (bps): `oai_mac_rx_bps`
- UL SNR: `oai_mac_snr_db`
- DL/UL BLER: `oai_mac_dl_bler`, `oai_mac_ul_bler`

## Save a logfile after iperf

You can export Prometheus data to CSV using the HTTP API. Example (last 5 minutes of downlink throughput):

```bash
curl -G "http://<VM-IP>:9090/api/v1/query_range" \
  --data-urlencode 'query=oai_mac_tx_bps' \
  --data-urlencode 'start=NOW-300s' \
  --data-urlencode 'end=NOW' \
  --data-urlencode 'step=1s' > tx_bps.json
```

Replace `NOW` with an RFC3339 timestamp if needed, e.g. `2025-02-01T12:00:00Z`.
