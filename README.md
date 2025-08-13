# JMeter Toolkit FastAPI

A modular toolkit to generate, execute, and monitor performance tests with Apache JMeter, plus site performance/security monitoring utilities. Built with FastAPI and Streamlit.

## Key Features
- CSV → JMX generator (template-driven)
- Postman Collection → JMX generator
- JMeter execution orchestration with results UI
- Real-time JMeter dashboard (Streamlit) for .jtl/.csv
- K6 editor (web UI)
- Regex generator utility
- LLM chat (helper)
- Monitoring: Performance & Security
  - Lighthouse metrics (Perf/Accessibility/Best Practices/SEO)
  - Security headers audit (OWASP Top 10 related)
  - JS library vulnerability detection (heuristic)
  - Optional SSL scan (sslscan)
  - Optional Nuclei scan
  - Optional authenticated OWASP checks (login flow, brute-force rate limiting signal, CSRF token presence, protected page access, cookie flags)

## Repository Layout
```
JMeter_Toolkit_FastAPI/
  app/                      # FastAPI app
    main.py                 # Routes registration
    routers/                # Feature routers (chat, k6, regex, scriptgen, monitoring)
    utils/                  # JMeter runner, parsers, dashboards, audit engine
    core/                   # (LLM utilities, prompts)
  templates/                # Jinja2 templates (UI pages)
  static/                   # CSS/JS/Images and sample data
  app/streamlit_dashboard.py# Streamlit real-time JMeter dashboard
  reports/                  # Generated audit reports (created on first run)
```

## Prerequisites
- Python 3.9+
- pip / venv
- Node.js (only if using Lighthouse; optional)
- Optional CLIs for extended scans:
  - Lighthouse: `npm i -g lighthouse`
  - Nuclei: install from `https://github.com/projectdiscovery/nuclei`
  - sslscan: install from your OS package manager

Recommended Python packages:
```
pip install fastapi uvicorn jinja2 python-multipart httpx beautifulsoup4
pip install streamlit pandas
```

## Run
- Start FastAPI (dev):
```
uvicorn app.main:app --reload --port 8000
```
- Start the Streamlit JMeter dashboard (separate terminal):
```
streamlit run app/streamlit_dashboard.py
```

Open `http://localhost:8000/home` in your browser.

---

## JMeter Real-time Dashboard
A Streamlit-based dashboard to visualize Apache JMeter results (.jtl/.csv) in real time.

### Features
- Drag-and-drop JMeter `.jtl`/`.csv` files
- Live tailing via on-disk file path
- Auto-refresh interval control
- Filters: time range and test label(s)
- Charts: hits/sec, avg response time (ms), throughput (tps), error rate (%)
- Summary metrics with latest values
- Sample dataset to run out-of-the-box

### Run
```
pip install streamlit pandas
streamlit run app/streamlit_dashboard.py
```
Dashboard URL: `http://localhost:8501`

Alternatively, access via the FastAPI UI page: Monitoring → JMeter Dashboard (embeds the Streamlit app).

### Data Source
- Drop a `.jtl` or `.csv` from JMeter into the sidebar uploader, or
- Provide the absolute file path to a live results file while a test is running

### Notes
- Sample data resides at `static/sample_data/jmeter_sample.csv`.
- The dashboard parses CSV and XML JTL formats.

---

## Monitoring: Performance & Security
The Monitoring section offers performance and security audits for a target website, with optional authenticated checks.

### Features
- Crawl same-origin pages to collect subsidiary URLs
- Performance audit
  - Lighthouse (scores and metrics: FCP, LCP, TTI, TBT, CLS)
  - Heuristic security-header check to flag best-practice gaps
  - JS library vulnerability hints by parsing script tags and versions
- Security audit
  - Security headers, cookie flags (Secure, HttpOnly, SameSite)
  - Optional SSL scan via `sslscan`
  - Optional Nuclei scan for known vulnerabilities
  - Optional authenticated OWASP checks (login flow)
    - CSRF token presence on login form
    - Brute-force rate limiting signal (status/Retry-After)
    - Protected page access pre/post login
    - Session cookie flags
    - Simple reflected input signals (XSS/SQLi) on login

### UI
- Monitoring → Performance: `GET /monitoring/performance`
- Monitoring → Security: `GET /monitoring/security`
- Submit the forms to run the audits. A short preview is shown; full reports saved to disk.

### Back-end Components
- `app/utils/audit_engine.py`
  - `WebCrawler`: collects same-origin links up to a limit (default 50)
  - Scanners implement a common `Scanner` interface
    - `LighthouseScanner` (requires lighthouse CLI)
    - `SecurityHeadersScanner` (OWASP-related headers)
    - `JsVulnerabilityScanner` (heuristic script version parsing)
    - `SslScanner` (requires sslscan)
    - `NucleiScanner` (requires nuclei)
  - `AuthTester`: optional login-protected flow checks
  - `ReportWriter`: writes JSON and HTML reports in `reports/<timestamp>/`

### Optional Tools
Install any of the following to enable deeper checks:
- Lighthouse: `npm i -g lighthouse`
- Nuclei: `https://github.com/projectdiscovery/nuclei`
- sslscan: via package manager

### Outputs
- Reports are saved per run in `reports/YYYYMMDD_HHMMSS/`:
  - `report.json`: machine-readable results
  - `report.html`: formatted, human-readable report

### Notes
- This utility is best-effort and non-invasive by default. For comprehensive pentesting, use dedicated tools under proper authorization.
- The crawler adheres to same-origin links to reduce risk; adjust in code if needed.

---

## Scripting & Execution

### CSV → JMX
- UI: `/csv-to-jmx`
- Upload a CSV and the app will generate a JMX using the template `templates/jmeter.jmx.j2`.
- Outputs are saved under `static/outputs/` and surfaced in the UI.

### Postman → JMX
- UI: `/postman-to-jmx`
- Upload a Postman collection; HTTP request groups are translated into Transaction Controllers and HTTP Samplers.
- Generates a `generated.jmx` in a temporary outputs directory for download.

### Execute JMeter
- UI: `/execute`
- Upload a `.jmx` file and trigger execution.
- The server spawns a run folder under `results/<run_id>/` and tracks status.
- HTML reports (if generated by JMeter command) are saved in the run directory.
- Status and a simple dashboard are available under:
  - `/status` (JSON)
  - `/metrics` (JSON)
  - `/dashboard` (HTML dashboard)
  - `/jmeter-log` (view current run `jmeter.log`)

### Notes
- Windows: ensure JMeter is installed and available on the PATH if running via command line from server utilities.
- Outputs and run artifacts live under `static/outputs/` and `results/` respectively.

---

## K6 Editor
A browser-based editor for crafting and previewing k6 scripts.

### UI
- Navigate to `K6 Editor` from the navbar or visit `/k6-editor`.

### Purpose
- Create and edit k6 scripts with a modern UI.
- Export scripts for load testing with k6.

### Notes
- Generated scripts may be saved under `static/outputs/` depending on usage.

---

## Regex Generator & LLM Chat

### Regex Generator
- UI: `/regex-generator`
- Helps generate robust regex patterns based on example input and expected values.
- Useful for correlation and data extraction in performance scripts.

### LLM Chat
- UI: `/chat`
- Assistant utility for brainstorming and quick guidance while building scripts/tests.

### Notes
- These utilities are optional helpers alongside the core JMeter features.

---

## Reports
- Monitoring runs write JSON and HTML reports to `reports/<YYYYMMDD_HHMMSS>/`.
- Each run is timestamped and self-contained.

## Notes
- Windows users: if using PowerShell, you may need execution policy set for running local tools.
- The UI includes a Monitoring menu with sub-items for Performance and Security pages. 