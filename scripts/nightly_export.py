#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import gzip
import json
import os
import subprocess
import sys
import time
from datetime import datetime, date, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


def load_env_file(path: Path) -> None:
    if not path.exists():
        raise FileNotFoundError(f"Env file not found: {path}")

    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


class ZabbixAPI:
    def __init__(self, url: str, token: str, auth_mode: str = "bearer") -> None:
        self.url = url
        self.token = token
        self.auth_mode = auth_mode
        self.session = requests.Session()
        self.request_id = 0

    def call(self, method: str, params: dict[str, Any]) -> Any:
        self.request_id += 1

        payload: dict[str, Any] = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params,
            "id": self.request_id,
        }

        headers = {"Content-Type": "application/json-rpc"}

        if self.auth_mode == "auth":
            payload["auth"] = self.token
        else:
            headers["Authorization"] = f"Bearer {self.token}"

        response = self.session.post(
            self.url,
            headers=headers,
            data=json.dumps(payload),
            timeout=120,
        )
        response.raise_for_status()

        data = response.json()
        if "error" in data:
            raise RuntimeError(f"Zabbix API error on {method}: {data['error']}")

        return data["result"]


def utc_day_bounds(day: date) -> tuple[int, int]:
    start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return int(start.timestamp()), int(end.timestamp())


def parse_day(value: str | None) -> date:
    if value:
        return date.fromisoformat(value)
    return datetime.now(timezone.utc).date() - timedelta(days=1)


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, sort_keys=True, default=str))


def upload_to_s3(local_dir: Path, bucket: str, prefix: str, endpoint: str, profile: str) -> None:
    target = f"s3://{bucket}/{prefix.rstrip('/')}/"
    cmd = [
        "aws",
        "--profile", profile,
        "--endpoint-url", endpoint,
        "s3", "sync",
        str(local_dir),
        target,
        "--only-show-errors",
    ]
    print(f"[INFO] Uploading {local_dir} -> {target}")
    subprocess.run(cmd, check=True)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Nightly Zabbix export for CNSM/NOMS 2027 study."
    )
    parser.add_argument("--env", default="/home/ubuntu/.cnsm2027/zabbix_export.env")
    parser.add_argument("--date", help="UTC date to export, format YYYY-MM-DD. Default: yesterday UTC.")
    parser.add_argument("--local-root", default="/home/ubuntu/cnsm2027/exports/zabbix")
    parser.add_argument("--no-upload", action="store_true")
    parser.add_argument("--auth-mode", choices=["bearer", "auth"], default="bearer")
    args = parser.parse_args()

    load_env_file(Path(args.env))

    zabbix_url = os.environ["ZABBIX_URL"]
    zabbix_token = os.environ["ZABBIX_API_TOKEN"]
    zabbix_group = os.environ.get("ZABBIX_GROUP", "cnsm2027-study")

    s3_bucket = os.environ["S3_BUCKET"]
    s3_endpoint = os.environ["S3_ENDPOINT"]
    aws_profile = os.environ.get("AWS_PROFILE", "ovh-cnsm")

    export_day = parse_day(args.date)
    time_from, time_till = utc_day_bounds(export_day)

    yyyy = f"{export_day.year:04d}"
    mm = f"{export_day.month:02d}"
    dd = f"{export_day.day:02d}"

    local_dir = Path(args.local_root) / yyyy / mm / dd
    ensure_dir(local_dir)

    api = ZabbixAPI(zabbix_url, zabbix_token, auth_mode=args.auth_mode)

    print(f"[INFO] Export date UTC: {export_day.isoformat()}")
    print(f"[INFO] Zabbix group: {zabbix_group}")

    groups = api.call("hostgroup.get", {
        "output": ["groupid", "name"],
        "filter": {"name": [zabbix_group]},
    })

    if not groups:
        raise RuntimeError(f"Zabbix host group not found: {zabbix_group}")

    groupid = groups[0]["groupid"]

    hosts = api.call("host.get", {
        "output": ["hostid", "host", "name"],
        "groupids": [groupid],
        "monitored_hosts": True,
        "sortfield": "host",
    })

    if not hosts:
        raise RuntimeError(f"No monitored hosts found in group: {zabbix_group}")

    host_by_id = {h["hostid"]: h for h in hosts}
    hostids = list(host_by_id.keys())

    print(f"[INFO] Hosts found: {len(hosts)}")

    items = api.call("item.get", {
        "output": ["itemid", "hostid", "name", "key_", "value_type", "delay", "status", "state"],
        "hostids": hostids,
        "monitored": True,
        "sortfield": "name",
    })

    items = [item for item in items if item.get("status") == "0"]
    item_by_id = {item["itemid"]: item for item in items}

    print(f"[INFO] Enabled monitored items found: {len(items)}")

    write_json(local_dir / "hosts.json", hosts)
    write_json(local_dir / "items.json", items)

    rows: list[dict[str, Any]] = []
    jsonl_path = local_dir / "history.jsonl.gz"

    started_at = datetime.now(timezone.utc)

    with gzip.open(jsonl_path, "wt", encoding="utf-8") as fh:
        for index, item in enumerate(items, start=1):
            itemid = item["itemid"]
            host = host_by_id[item["hostid"]]
            value_type = int(item["value_type"])

            if index % 50 == 0 or index == 1:
                print(f"[INFO] Exporting item {index}/{len(items)}")

            history = api.call("history.get", {
                "output": "extend",
                "history": value_type,
                "itemids": [itemid],
                "time_from": time_from,
                "time_till": time_till,
                "sortfield": "clock",
                "sortorder": "ASC",
            })

            for point in history:
                clock = int(point["clock"])
                ns = int(point.get("ns", 0))
                record = {
                    "clock": clock,
                    "clock_iso": datetime.fromtimestamp(clock, tz=timezone.utc).isoformat(),
                    "ns": ns,
                    "hostid": item["hostid"],
                    "host": host["host"],
                    "itemid": itemid,
                    "item_name": item["name"],
                    "item_key": item["key_"],
                    "value_type": value_type,
                    "value": point.get("value"),
                }
                rows.append(record)
                fh.write(json.dumps(record, ensure_ascii=False) + "\n")

            time.sleep(0.02)

    print(f"[INFO] History rows exported: {len(rows)}")

    parquet_path = local_dir / "history.parquet"
    parquet_written = False

    try:
        import pandas as pd

        if rows:
            df = pd.DataFrame(rows)
            df.to_parquet(parquet_path, index=False)
            parquet_written = True
            print(f"[INFO] Parquet written: {parquet_path}")
        else:
            print("[WARN] No rows found. Parquet not written.")
    except Exception as exc:
        print(f"[WARN] Could not write Parquet: {exc}")

    finished_at = datetime.now(timezone.utc)

    manifest = {
        "export_day_utc": export_day.isoformat(),
        "time_from": time_from,
        "time_till": time_till,
        "zabbix_url": zabbix_url,
        "zabbix_group": zabbix_group,
        "host_count": len(hosts),
        "item_count": len(items),
        "history_row_count": len(rows),
        "jsonl_gzip": jsonl_path.name,
        "parquet": parquet_path.name if parquet_written else None,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": finished_at.isoformat(),
    }

    write_json(local_dir / "manifest.json", manifest)

    # Simple CSV summary for quick inspection
    with (local_dir / "summary.csv").open("w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["export_day_utc", "host_count", "item_count", "history_row_count"])
        writer.writerow([export_day.isoformat(), len(hosts), len(items), len(rows)])

    if not args.no_upload:
        s3_prefix = f"raw/zabbix/daily/{yyyy}/{mm}/{dd}"
        upload_to_s3(local_dir, s3_bucket, s3_prefix, s3_endpoint, aws_profile)

    print("[INFO] Export completed successfully.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
