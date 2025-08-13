import io
import os
from typing import Dict, Iterable, Optional, Tuple

import pandas as pd
from xml.etree import ElementTree as ET


def _read_csv_flexible(csv_source: io.BytesIO | str) -> pd.DataFrame:
	"""Read JMeter CSV/JTL with flexible columns and return raw DataFrame.

	This supports sources with or without headers. If headers are missing, we attempt
	to assign common JMeter column names.
	"""
	# Try to read with header first
	try:
		return pd.read_csv(csv_source)
	except Exception:
		# Retry assuming no header
		csv_source2 = csv_source
		if isinstance(csv_source, io.BytesIO):
			csv_source2 = io.BytesIO(csv_source.getvalue())
		return pd.read_csv(
			csv_source2,
			header=None,
			names=[
				"timeStamp",
				"elapsed",
				"label",
				"responseCode",
				"responseMessage",
				"threadName",
				"dataType",
				"success",
				"failureMessage",
				"bytes",
				"sentBytes",
				"grpThreads",
				"allThreads",
				"URL",
				"Latency",
				"IdleTime",
				"Connect",
			],
		)


def _read_xml_jtl(xml_source: io.BytesIO | str) -> pd.DataFrame:
	"""Parse XML JTL files and extract a minimal set of fields.

	We support both httpSample and sample elements and capture:
	- ts (timestamp in ms), t (elapsed), s (success), lb (label), rc (response code)
	"""
	if isinstance(xml_source, str) and os.path.exists(xml_source):
		tree = ET.parse(xml_source)
		root = tree.getroot()
	else:
		# BytesIO or raw text
		content = xml_source.getvalue() if isinstance(xml_source, io.BytesIO) else xml_source
		root = ET.fromstring(content)

	records = []
	for elem in root.iter():
		if elem.tag in {"httpSample", "sample"}:
			try:
				ts = int(elem.attrib.get("ts"))
				t = int(elem.attrib.get("t"))
				label = elem.attrib.get("lb", "")
				rc = elem.attrib.get("rc", "")
				success_attr = elem.attrib.get("s", "true")
				success = str(success_attr).lower() in {"true", "1", "t", "y"}
				records.append(
					{
						"timeStamp": ts,
						"elapsed": t,
						"label": label,
						"responseCode": rc,
						"success": success,
					}
				)
			except Exception:
				# Skip malformed elements
				continue
	return pd.DataFrame.from_records(records)


def load_jmeter_results(source: io.BytesIO | str) -> pd.DataFrame:
	"""Load JMeter results from CSV or XML JTL.

	- If `source` is a path string, we infer format from extension and/or content
	- If `source` is a BytesIO from an uploader, we try CSV first, then XML
	"""
	if isinstance(source, str) and os.path.exists(source):
		lower = source.lower()
		if lower.endswith(".csv") or lower.endswith(".jtl"):
			# Try CSV first
			try:
				df = _read_csv_flexible(source)
				if not df.empty:
					return df
			except Exception:
				pass
			# Fallback to XML
			try:
				return _read_xml_jtl(source)
			except Exception as exc:
				raise ValueError(f"Failed to parse JMeter file: {exc}")
		# Unknown extension; still attempt CSV then XML
		try:
			return _read_csv_flexible(source)
		except Exception:
			return _read_xml_jtl(source)

	# Bytes/stream from uploader
	if isinstance(source, (io.BytesIO, bytes)):
		buffer = source if isinstance(source, io.BytesIO) else io.BytesIO(source)
		# Try CSV first
		try:
			buffer.seek(0)
			df = _read_csv_flexible(buffer)
			if not df.empty:
				return df
		except Exception:
			pass
		# Fallback to XML
		buffer.seek(0)
		return _read_xml_jtl(buffer)


def normalize_results(df: pd.DataFrame) -> pd.DataFrame:
	"""Normalize raw DataFrame to a canonical schema required by the dashboard.

	Expected output columns:
	- timestamp (datetime64[ns])
	- elapsed (int milliseconds)
	- label (string)
	- success (bool)
	- responseCode (string, optional)
	"""
	working = df.copy()

	# Standardize column names (case-insensitive match)
	def _find(name_options: Iterable[str]) -> Optional[str]:
		lower_cols = {c.lower(): c for c in working.columns}
		for opt in name_options:
			if opt.lower() in lower_cols:
				return lower_cols[opt.lower()]
		return None

	timestamp_col = _find(["timeStamp", "timestamp", "ts"]) or "timeStamp"
	elapsed_col = _find(["elapsed", "t"]) or "elapsed"
	label_col = _find(["label", "lb"]) or "label"
	success_col = _find(["success", "s"]) or "success"
	response_code_col = _find(["responseCode", "rc"]) or None

	# Coerce timestamp to datetime (JMeter uses epoch ms)
	if timestamp_col in working.columns:
		working["timestamp"] = pd.to_datetime(working[timestamp_col], unit="ms", errors="coerce")
	else:
		raise ValueError("Missing timestamp column in JMeter results")

	# Elapsed time (ms)
	if elapsed_col in working.columns:
		working["elapsed"] = pd.to_numeric(working[elapsed_col], errors="coerce")
	else:
		raise ValueError("Missing elapsed column in JMeter results")

	# Label (test name)
	working["label"] = working[label_col].astype(str) if label_col in working.columns else ""

	# Success boolean
	if success_col in working.columns:
		def _to_bool(val) -> bool:
			if isinstance(val, (int, float)):
				return bool(val)
			text = str(val).strip().lower()
			return text in {"true", "1", "t", "y"}
		working["success"] = working[success_col].map(_to_bool)
	else:
		# Derive from response code if available, else assume success
		if response_code_col and response_code_col in working.columns:
			working["success"] = working[response_code_col].astype(str).str.startswith("2")
		else:
			working["success"] = True

	# Response code if available
	if response_code_col and response_code_col in working.columns:
		working["responseCode"] = working[response_code_col].astype(str)

	# Keep only canonical columns
	canonical_cols = ["timestamp", "elapsed", "label", "success"]
	if "responseCode" in working.columns:
		canonical_cols.append("responseCode")
	working = working[canonical_cols].dropna(subset=["timestamp", "elapsed"]).sort_values("timestamp")

	return working.reset_index(drop=True)


def filter_results(
	df: pd.DataFrame,
	label_filter: Optional[Iterable[str]] = None,
	time_range: Optional[Tuple[pd.Timestamp, pd.Timestamp]] = None,
) -> pd.DataFrame:
	"""Apply label and time range filters to normalized results."""
	filtered = df
	if label_filter:
		allowed = set(label_filter)
		filtered = filtered[filtered["label"].isin(allowed)]
	if time_range:
		start, end = time_range
		filtered = filtered[(filtered["timestamp"] >= start) & (filtered["timestamp"] <= end)]
	return filtered.reset_index(drop=True)


def compute_time_series_metrics(df: pd.DataFrame, resample_freq: str = "1S") -> Dict[str, pd.DataFrame]:
	"""Compute per-interval time series metrics.

	Returns a dict of DataFrames indexed by timestamp with a single value column per metric.
	- hits_per_second: total requests per second
	- avg_response_time_ms: mean elapsed per second
	- throughput_tps: successful requests per second
	- error_rate_percent: failures / total per second * 100
	"""
	if df.empty:
		index = pd.date_range(pd.Timestamp.utcnow().floor("S"), periods=1, freq=resample_freq)
		empty = pd.DataFrame(index=index)
		return {
			"hits_per_second": empty.assign(value=0),
			"avg_response_time_ms": empty.assign(value=0.0),
			"throughput_tps": empty.assign(value=0.0),
			"error_rate_percent": empty.assign(value=0.0),
		}

	indexed = df.set_index("timestamp")
	counts = indexed["elapsed"].resample(resample_freq).count().rename("value")
	avg_elapsed = indexed["elapsed"].resample(resample_freq).mean().fillna(0.0).rename("value")
	success_counts = indexed[indexed["success"]]["elapsed"].resample(resample_freq).count().rename("value")
	failure_counts = indexed[~indexed["success"]]["elapsed"].resample(resample_freq).count().rename("value")

	# Align series and compute error rate
	aligned_total, aligned_failures = counts.align(failure_counts, fill_value=0)
	error_rate = (aligned_failures / aligned_total.replace({0: pd.NA})).astype(float) * 100.0
	error_rate = error_rate.fillna(0.0).rename("value")

	return {
		"hits_per_second": counts.to_frame(),
		"avg_response_time_ms": avg_elapsed.to_frame(),
		"throughput_tps": success_counts.fillna(0).astype(float).to_frame(),
		"error_rate_percent": error_rate.to_frame(),
	}


def compute_summary(df: pd.DataFrame, series: Dict[str, pd.DataFrame]) -> Dict[str, float]:
	"""Compute latest snapshot values for summary display."""
	latest = {}
	for key, s in series.items():
		if s.empty:
			latest[key] = 0.0
			continue
		latest_val = s.dropna().iloc[-1]["value"] if not s.dropna().empty else 0.0
		latest[key] = float(latest_val)

	# Also compute overall current average response time across filtered data
	if df.empty:
		latest["overall_avg_response_time_ms"] = 0.0
	else:
		latest["overall_avg_response_time_ms"] = float(pd.to_numeric(df["elapsed"], errors="coerce").dropna().mean())
	return latest 