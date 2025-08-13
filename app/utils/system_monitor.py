import csv
import datetime
import os
import time
from typing import Optional, Dict, Any

try:
	import psutil  # type: ignore
except ImportError:
	psutil = None  # type: ignore


def run_system_monitor(interval_seconds: int, duration_seconds: int, label: Optional[str] = None) -> str:
	"""Sample CPU, memory, and disk usage and write to CSV under reports.

	Returns the CSV file path.
	"""
	os.makedirs("reports", exist_ok=True)
	stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
	folder = os.path.join("reports", f"system_{stamp}")
	os.makedirs(folder, exist_ok=True)
	base = f"system_metrics{('_' + label) if label else ''}.csv"
	csv_path = os.path.join(folder, base)

	fields = ["timestamp", "cpu_percent", "mem_percent", "disk_percent"]
	start = time.time()
	with open(csv_path, "w", newline="", encoding="utf-8") as fh:
		writer = csv.DictWriter(fh, fieldnames=fields)
		writer.writeheader()
		while time.time() - start < duration_seconds:
			if psutil is None:
				row = {
					"timestamp": datetime.datetime.now().isoformat(),
					"cpu_percent": -1,
					"mem_percent": -1,
					"disk_percent": -1,
				}
			else:
				row = {
					"timestamp": datetime.datetime.now().isoformat(),
					"cpu_percent": psutil.cpu_percent(interval=None),
					"mem_percent": psutil.virtual_memory().percent,
					"disk_percent": psutil.disk_usage("/").percent if os.name != "nt" else psutil.disk_usage("C:\\").percent,
				}
			writer.writerow(row)
			time.sleep(max(0, interval_seconds))

	return csv_path


def get_system_snapshot() -> Dict[str, Any]:
	"""Return a snapshot of current CPU, memory, and disk utilization."""
	if psutil is None:
		return {
			"timestamp": datetime.datetime.now().isoformat(),
			"cpu_percent": -1,
			"mem_percent": -1,
			"disk_percent": -1,
			"note": "psutil not installed",
		}
	return {
		"timestamp": datetime.datetime.now().isoformat(),
		"cpu_percent": psutil.cpu_percent(interval=None),
		"mem_percent": psutil.virtual_memory().percent,
		"disk_percent": psutil.disk_usage("/").percent if os.name != "nt" else psutil.disk_usage("C:\\").percent,
	} 