import subprocess, csv, os, json, datetime, shutil

jmeter_status_tracker = {"status": "Not Started"}

# 🔧 Absolute path to your JMeter binary
JMETER_PATH = "/Users/jayanth/Downloads/apache-jmeter-5.6.3/bin/jmeter"


def run_jmeter(jmx_path: str, output_dir: str, html_report_dir: str) -> None:
    """Run a JMeter test in a background thread.

    * Streams *all* JMeter STDOUT / STDERR into <api_folder>/jmeter.log so it can be
      tailed live by the front‑end.
    * Writes a concise execution summary into <api_folder>/summary.log after the
      process ends (so the Execute page can still show just the summary block).
    * Updates a metrics JSON so the dashboard can poll live data.
    """
    api_name   = os.path.splitext(os.path.basename(jmx_path))[0]
    timestamp  = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    api_folder = os.path.join(output_dir, f"{api_name}_{timestamp}")
    os.makedirs(api_folder, exist_ok=True)

    # Pre‑create paths ---------------------------------------------------------
    result_jtl     = os.path.join(api_folder, "test_run.jtl")
    jmeter_log     = os.path.join(api_folder, "jmeter.log")
    summary_path   = os.path.join(api_folder, "summary.log")
    metrics_path   = os.path.join("results", "status_metrics.json")  # global

    # Reset trackers
    with open(metrics_path, "w") as f:
        json.dump({"vusers": 0, "transactions": 0,
                   "avg_response_time": 0, "errors": 0}, f)
    jmeter_status_tracker["status"] = "Running"

    # -------------------------------------------------------------------------
    cmd = [
        JMETER_PATH,
        "-n",                     # Non‑GUI mode
        "-t", jmx_path,           # Test plan
        "-l", result_jtl,         # JTL output
        "-e", "-o", html_report_dir,              # HTML dashboard
        "-Jjmeterengine.force.system.exit=true",
        "-Jjmeter.save.saveservice.output_format=csv",
        "-Djava.awt.headless=true",
        "-Jsummariser.interval=2",                 # 2‑second summary
        "-j", jmeter_log                           # Framework log file
    ]

    # -------------------------------------------------------------------------
    # Stream everything directly into jmeter.log --------------------------------
    with open(jmeter_log, "w") as lf:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=lf, text=True)
        proc.wait()  # block until JMeter finishes

    # -------------------------------------------------------------------------
    # After exit – build concise summary from the streamed log ------------------
    with open(jmeter_log, "r") as lf:
        full_log = lf.read()

    summary_lines = []
    for line in full_log.splitlines():
        if line.startswith("summary =") or line.startswith("STDOUT:") \
           or line.startswith("STDERR:") or line.startswith("RETURN CODE"):
            summary_lines.append(line)

    summary_text  = "\n".join(summary_lines) if summary_lines else full_log[-1500:]
    summary_text += f"\nRETURN CODE: {proc.returncode}\n"

    with open(summary_path, "w") as sf:
        sf.write(summary_text)

    # -------------------------------------------------------------------------
    # Parse metrics & update JSON ---------------------------------------------
    if os.path.exists(result_jtl):
        try:
            metrics = parse_jtl(result_jtl)
            with open(metrics_path, "w") as f:
                json.dump({
                    "vusers": 1,  # basic single‑node run; adjust if needed
                    "transactions": metrics["total_requests"],
                    "avg_response_time": metrics["avg_response_time"],
                    "errors": metrics["error_rate"]
                }, f)
        except Exception as e:
            print("Error parsing JTL:", e)

    # Set final status ---------------------------------------------------------
    if proc.returncode == 0:
        jmeter_status_tracker["status"] = "Completed"
    else:
        jmeter_status_tracker["status"] = f"Failed (exit {proc.returncode})"


def parse_jtl(jtl_path: str):
    """Return basic stats from a JTL (CSV) file."""
    with open(jtl_path, newline="") as f:
        reader = csv.DictReader(f)
        samples = list(reader)

    total       = len(samples) or 1  # avoid div/0
    success_cnt = sum(1 for r in samples if r['success'] == 'true')
    avg_resp    = sum(float(r['elapsed']) for r in samples) / total
    error_rate  = 100 * (1 - success_cnt / total)

    return {
        "total_requests": total,
        "avg_response_time": round(avg_resp, 2),
        "error_rate": round(error_rate, 2)
    }
