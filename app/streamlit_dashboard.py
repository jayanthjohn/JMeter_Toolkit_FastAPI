import io
import os
import time
from datetime import timedelta
from typing import Optional

import pandas as pd
import streamlit as st

from app.utils.jmeter_dashboard_utils import (
	compute_time_series_metrics,
	filter_results,
	load_jmeter_results,
	normalize_results,
)


# Basic page config
st.set_page_config(page_title="JMeter Live Dashboard", layout="wide")


@st.cache_data(show_spinner=False)
def load_sample_csv() -> pd.DataFrame:
	"""Provide a small sample dataset for out-of-the-box experience."""
	sample_path = os.path.join("static", "sample_data", "jmeter_sample.csv")
	if os.path.exists(sample_path):
		return pd.read_csv(sample_path)
	# Generate synthetic sample if file missing
	now = pd.Timestamp.utcnow().floor("S")
	rows = []
	for i in range(300):
		rows.append(
			{
				"timeStamp": int((now - pd.Timedelta(seconds=300 - i)).timestamp() * 1000),
				"elapsed": int(80 + (i % 10) * 5),
				"label": "Sample API",
				"responseCode": "200" if i % 13 != 0 else "500",
				"success": (i % 13 != 0),
			}
		)
	return pd.DataFrame(rows)


@st.cache_data(show_spinner=False)
def parse_results(file_bytes: Optional[bytes], default_df: pd.DataFrame) -> pd.DataFrame:
	"""Parse uploaded file or fallback to default sample DataFrame."""
	if file_bytes is None:
		return normalize_results(default_df)
	try:
		return normalize_results(load_jmeter_results(io.BytesIO(file_bytes)))
	except Exception as exc:
		st.warning(f"Failed to parse uploaded file, using sample data. Error: {exc}")
		return normalize_results(default_df)


# Sidebar controls
with st.sidebar:
	st.title("Controls")
	refresh_seconds = st.slider("Auto-refresh interval (s)", min_value=2, max_value=30, value=5)
	file_path = st.text_input("JMeter file path (.jtl/.csv)")
	uploaded_file = st.file_uploader("Or drop JMeter .jtl/.csv", type=["jtl", "csv"], accept_multiple_files=False)
	default_data = load_sample_csv()
	# Priority: file path on disk > uploaded file > sample data
	parsed_df: pd.DataFrame
	if file_path and os.path.exists(file_path):
		try:
			parsed_df = normalize_results(load_jmeter_results(file_path))
		except Exception as exc:
			st.warning(f"Failed to read path '{file_path}'. Falling back to uploaded/sample. Error: {exc}")
			parsed_df = parse_results(uploaded_file.getvalue() if uploaded_file else None, default_data)
	else:
		parsed_df = parse_results(uploaded_file.getvalue() if uploaded_file else None, default_data)

	# Time range filter
	if parsed_df.empty:
		min_time = pd.Timestamp.utcnow() - pd.Timedelta(minutes=5)
		max_time = pd.Timestamp.utcnow()
	else:
		min_time = parsed_df["timestamp"].min()
		max_time = parsed_df["timestamp"].max()
	default_start = max_time - pd.Timedelta(minutes=5)
	if default_start < min_time:
		default_start = min_time
	start_time, end_time = st.slider(
		"Time range",
		min_value=min_time.to_pydatetime(),
		max_value=max_time.to_pydatetime(),
		value=(default_start.to_pydatetime(), max_time.to_pydatetime()),
		step=timedelta(seconds=1),
	)

	# Label filter
	labels = sorted(parsed_df["label"].dropna().unique().tolist()) if not parsed_df.empty else []
	selected_labels = st.multiselect("Test name(s)", options=labels, default=labels)

	st.caption("Provide a file path for live tailing, or drag-and-drop a file to analyze once. Charts update automatically.")

# Title
col_title, col_spacer, col_refresh = st.columns([6, 3, 1])
with col_title:
	st.markdown("### JMeter Real-time Dashboard")
with col_refresh:
	st.button("Refresh", type="primary")

# Apply filters
start_ts = pd.Timestamp(start_time).tz_localize(None)
end_ts = pd.Timestamp(end_time).tz_localize(None)
filtered_df = filter_results(parsed_df, label_filter=selected_labels, time_range=(start_ts, end_ts))

# Compute metrics
series = compute_time_series_metrics(filtered_df, resample_freq="1S")

# Summary section
st.markdown("#### Summary")
s1, s2, s3, s4 = st.columns(4)
last_hits = series["hits_per_second"]["value"].iloc[-1] if not series["hits_per_second"].empty else 0
last_avg_rt = series["avg_response_time_ms"]["value"].iloc[-1] if not series["avg_response_time_ms"].empty else 0
last_tps = series["throughput_tps"]["value"].iloc[-1] if not series["throughput_tps"].empty else 0
last_err = series["error_rate_percent"]["value"].iloc[-1] if not series["error_rate_percent"].empty else 0
with s1:
	st.metric("Hit rate (1s)", f"{last_hits:.0f} req/s")
with s2:
	st.metric("Avg response time (1s)", f"{last_avg_rt:.0f} ms", help="Per-second mean elapsed time")
with s3:
	st.metric("Throughput (1s)", f"{last_tps:.0f} tps")
with s4:
	st.metric("Error rate (1s)", f"{last_err:.1f} %")

# Charts
st.markdown("#### Charts")

c1, c2 = st.columns(2)
with c1:
	st.line_chart(series["hits_per_second"], y="value", use_container_width=True)
with c2:
	st.line_chart(series["avg_response_time_ms"], y="value", use_container_width=True)

c3, c4 = st.columns(2)
with c3:
	st.line_chart(series["throughput_tps"], y="value", use_container_width=True)
with c4:
	st.bar_chart(series["error_rate_percent"], y="value", use_container_width=True)

# Raw table (optional expander)
with st.expander("View raw filtered data"):
	st.dataframe(filtered_df.tail(1000), use_container_width=True)

# Footer and auto-refresh
st.caption("Updated every few seconds. Use the sidebar to upload or tail a JMeter results file and filter by time range and test name.")
with st.spinner(f"Auto-refreshing in {refresh_seconds}s …"):
	time.sleep(refresh_seconds)
	st.experimental_rerun() 