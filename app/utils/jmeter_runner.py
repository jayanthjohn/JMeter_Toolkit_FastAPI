import subprocess, time, csv
import os, shutil  # ensure these are at the top if not already
import datetime

jmeter_status_tracker = {"status": "Not Started"}

JMETER_PATH = "/Users/jayanth/Downloads/apache-jmeter-5.6.3/bin/jmeter"  # full path

def run_jmeter(jmx_path, output_dir, html_report_dir):
    import datetime
    api_name = os.path.splitext(os.path.basename(jmx_path))[0]
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    api_folder = os.path.join(output_dir, f"{api_name}_{timestamp}")
    os.makedirs(api_folder, exist_ok=True)
    jmeter_status_tracker["status"] = "Running"
    result_jtl = os.path.join(api_folder, "test_run.jtl")

    try:
        cmd = [
            JMETER_PATH,
            "-n",
            "-t", jmx_path,
            "-l", result_jtl,
            "-e", "-o", html_report_dir,
            "-Jjmeterengine.force.system.exit=true",
            "-Jjmeter.save.saveservice.output_format=csv",
            "-Djava.awt.headless=true"
        ]
        completed = subprocess.run(cmd, capture_output=True, text=True)
        print("STDOUT:\n", completed.stdout)
        print("STDERR:\n", completed.stderr)
        print("RETURN CODE:", completed.returncode)
        if completed.returncode == 0:
            jmeter_status_tracker["status"] = "Completed"
        else:
            jmeter_status_tracker["status"] = f"Failed: Exit code {completed.returncode}, Error: {completed.stderr[:200]}"
    except Exception as e:
        jmeter_status_tracker["status"] = f"Error: {str(e)}"

def parse_jtl(jtl_path):
    with open(jtl_path, newline='') as f:
        reader = csv.DictReader(f)
        samples = list(reader)
    total = len(samples)
    success = sum(1 for r in samples if r['success'] == 'true')
    avg_resp = sum(float(r['elapsed']) for r in samples) / total
    error_rate = 100 * (1 - success / total)
    return {
        "total_requests": total,
        "avg_response_time": avg_resp,
        "error_rate": round(error_rate, 2)
    }