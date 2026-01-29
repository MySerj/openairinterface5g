#!/usr/bin/env python3
import argparse
import http.server
import re
import socketserver
import threading
import time
from pathlib import Path


def _parse_float(value: str) -> float:
    try:
        return float(value)
    except ValueError:
        return 0.0


class MacStatsSnapshot:
    def __init__(self) -> None:
        self.cqi = {}
        self.ri = {}
        self.snr_db = {}
        self.dl_bler = {}
        self.ul_bler = {}
        self.tx_bytes = {}
        self.rx_bytes = {}


class MacStatsExporter:
    def __init__(self, log_path: Path) -> None:
        self.log_path = log_path
        self._lock = threading.Lock()
        self._last_tx = {}
        self._last_rx = {}
        self._last_ts = {}
        self._last_rates = {}

        self._regex_cqi = re.compile(r"UE (?P<rnti>[0-9a-fA-F]{4}): CQI (?P<cqi>\d+), RI (?P<ri>\d+)")
        self._regex_ul = re.compile(r"UE (?P<rnti>[0-9a-fA-F]{4}): ulsch_rounds .* BLER (?P<bler>[0-9.]+) .* SNR (?P<snr_int>\d+)\.(?P<snr_dec>\d+) dB")
        self._regex_dl = re.compile(r"UE (?P<rnti>[0-9a-fA-F]{4}): dlsch_rounds .* BLER (?P<bler>[0-9.]+) ")
        self._regex_mac = re.compile(r"UE (?P<rnti>[0-9a-fA-F]{4}): MAC:\s+TX\s+(?P<tx_bytes>\d+)\s+RX\s+(?P<rx_bytes>\d+)\s+bytes")

    def _read_log(self) -> str:
        try:
            return self.log_path.read_text(encoding="utf-8", errors="ignore")
        except FileNotFoundError:
            return ""

    def _parse_snapshot(self, text: str) -> MacStatsSnapshot:
        snap = MacStatsSnapshot()
        for line in text.splitlines():
            match = self._regex_cqi.search(line)
            if match:
                rnti = match.group("rnti")
                snap.cqi[rnti] = int(match.group("cqi"))
                snap.ri[rnti] = int(match.group("ri"))
                continue

            match = self._regex_ul.search(line)
            if match:
                rnti = match.group("rnti")
                snr = float(f"{match.group('snr_int')}.{match.group('snr_dec')}")
                snap.snr_db[rnti] = snr
                snap.ul_bler[rnti] = _parse_float(match.group("bler"))
                continue

            match = self._regex_dl.search(line)
            if match:
                rnti = match.group("rnti")
                snap.dl_bler[rnti] = _parse_float(match.group("bler"))
                continue

            match = self._regex_mac.search(line)
            if match:
                rnti = match.group("rnti")
                snap.tx_bytes[rnti] = int(match.group("tx_bytes"))
                snap.rx_bytes[rnti] = int(match.group("rx_bytes"))

        return snap

    def _compute_rates(self, snap: MacStatsSnapshot) -> None:
        now = time.time()
        for rnti, tx in snap.tx_bytes.items():
            last = self._last_tx.get(rnti)
            last_ts = self._last_ts.get(rnti)
            if last is not None and last_ts is not None and now > last_ts:
                self._last_rates[(rnti, "tx")] = (tx - last) * 8.0 / (now - last_ts)
            self._last_tx[rnti] = tx
            self._last_ts[rnti] = now

        for rnti, rx in snap.rx_bytes.items():
            last = self._last_rx.get(rnti)
            last_ts = self._last_ts.get(rnti)
            if last is not None and last_ts is not None and now > last_ts:
                self._last_rates[(rnti, "rx")] = (rx - last) * 8.0 / (now - last_ts)
            self._last_rx[rnti] = rx
            self._last_ts[rnti] = now

    def collect(self) -> str:
        with self._lock:
            text = self._read_log()
            snap = self._parse_snapshot(text)
            self._compute_rates(snap)

            lines = [
                "# HELP oai_mac_cqi Wideband CQI reported by UE",
                "# TYPE oai_mac_cqi gauge",
            ]
            for rnti, cqi in snap.cqi.items():
                lines.append(f'oai_mac_cqi{{rnti="{rnti}"}} {cqi}')

            lines.extend([
                "# HELP oai_mac_ri Rank indicator reported by UE",
                "# TYPE oai_mac_ri gauge",
            ])
            for rnti, ri in snap.ri.items():
                lines.append(f'oai_mac_ri{{rnti="{rnti}"}} {ri}')

            lines.extend([
                "# HELP oai_mac_snr_db Uplink SNR observed by gNB",
                "# TYPE oai_mac_snr_db gauge",
            ])
            for rnti, snr in snap.snr_db.items():
                lines.append(f'oai_mac_snr_db{{rnti="{rnti}"}} {snr}')

            lines.extend([
                "# HELP oai_mac_dl_bler Downlink BLER",
                "# TYPE oai_mac_dl_bler gauge",
            ])
            for rnti, bler in snap.dl_bler.items():
                lines.append(f'oai_mac_dl_bler{{rnti="{rnti}"}} {bler}')

            lines.extend([
                "# HELP oai_mac_ul_bler Uplink BLER",
                "# TYPE oai_mac_ul_bler gauge",
            ])
            for rnti, bler in snap.ul_bler.items():
                lines.append(f'oai_mac_ul_bler{{rnti="{rnti}"}} {bler}')

            lines.extend([
                "# HELP oai_mac_tx_bytes Total downlink bytes transmitted by gNB",
                "# TYPE oai_mac_tx_bytes gauge",
            ])
            for rnti, tx in snap.tx_bytes.items():
                lines.append(f'oai_mac_tx_bytes{{rnti="{rnti}"}} {tx}')

            lines.extend([
                "# HELP oai_mac_rx_bytes Total uplink bytes received by gNB",
                "# TYPE oai_mac_rx_bytes gauge",
            ])
            for rnti, rx in snap.rx_bytes.items():
                lines.append(f'oai_mac_rx_bytes{{rnti="{rnti}"}} {rx}')

            lines.extend([
                "# HELP oai_mac_tx_bps Estimated downlink throughput in bits/sec",
                "# TYPE oai_mac_tx_bps gauge",
            ])
            for (rnti, direction), rate in self._last_rates.items():
                if direction == "tx":
                    lines.append(f'oai_mac_tx_bps{{rnti="{rnti}"}} {rate}')

            lines.extend([
                "# HELP oai_mac_rx_bps Estimated uplink throughput in bits/sec",
                "# TYPE oai_mac_rx_bps gauge",
            ])
            for (rnti, direction), rate in self._last_rates.items():
                if direction == "rx":
                    lines.append(f'oai_mac_rx_bps{{rnti="{rnti}"}} {rate}')

            return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Expose OAI nrMAC_stats.log metrics for Prometheus.")
    parser.add_argument("--log", default="nrMAC_stats.log", help="Path to nrMAC_stats.log")
    parser.add_argument("--listen", default="0.0.0.0", help="Listen address")
    parser.add_argument("--port", type=int, default=9109, help="Listen port")
    args = parser.parse_args()

    exporter = MacStatsExporter(Path(args.log))

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in ("/metrics", "/"):
                self.send_response(404)
                self.end_headers()
                return
            body = exporter.collect().encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; version=0.0.4")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):
            return

    with socketserver.ThreadingTCPServer((args.listen, args.port), Handler) as httpd:
        print(f"Serving metrics on http://{args.listen}:{args.port}/metrics")
        httpd.serve_forever()


if __name__ == "__main__":
    main()
