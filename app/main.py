from jinja2 import Environment, FileSystemLoader
from fastapi import Request
from fastapi.responses import HTMLResponse
from .utils.regex_utils import build_regex_from_example
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from .utils.postman_parser import parse_postman_collection
from .routers import regex, scriptgen, chat, k6_editor
# Additional imports for JMeter execution
from fastapi import BackgroundTasks
from fastapi.responses import JSONResponse
from .utils.jmeter_runner import run_jmeter, parse_jtl, jmeter_status_tracker

app = FastAPI()
from fastapi import UploadFile, File, Form
from fastapi.responses import FileResponse
import shutil
import uuid
import csv, os
from .routers.scriptgen import generate_jmx_from_csv_using_template
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
import os
templates.env.filters["basename"] = lambda path: os.path.basename(path)

# Routers
app.include_router(regex.router)
app.include_router(scriptgen.router)
app.include_router(chat.router)
app.include_router(k6_editor.router)

import json

@app.get("/metrics")
def get_metrics():
    with open("results/status_metrics.json") as f:
        return json.load(f)

@app.get("/")
def read_root():
    return {"msg": "JMeter Toolkit FastAPI version running."}


# UI Home route
@app.get("/home", response_class=HTMLResponse)
def render_home(request: Request):
    return templates.TemplateResponse("base.html", {"request": request})

# CSV to JMX UI route
@app.get("/csv-to-jmx", response_class=HTMLResponse)
def render_csv_to_jmx(request: Request):
    return templates.TemplateResponse("csv_to_jmx.html", {"request": request})


# Generate scripts endpoint
@app.post("/generate-scripts")
async def generate_scripts(
    request: Request,
    file: UploadFile = File(...),
    output_types: list[str] = Form(...)
):
    temp_file_name = f"temp_{uuid.uuid4()}.csv"
    output_paths = []

    with open(temp_file_name, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    if "JMeter (.jmx)" in output_types:
        # Derive base file name from first row's API or Label column
        with open(temp_file_name, newline="") as fh:
            first_row = next(csv.DictReader(fh), {})
            raw_name = (
                (first_row.get("name") or first_row.get("Name"))
                or (first_row.get("API") or first_row.get("Api"))
                or first_row.get("Label")
                or f"generated_{uuid.uuid4()}"
            )
        safe_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in raw_name)[:50]
        jmx_output = f"static/outputs/{safe_name}.jmx"
        os.makedirs(os.path.dirname(jmx_output), exist_ok=True)

        # Generate the real JMX using the template-based helper
        generate_jmx_from_csv_using_template(temp_file_name, jmx_output)
        output_paths.append(jmx_output)

    if "K6 (.js)" in output_types:
        k6_output = f"static/outputs/generated_{uuid.uuid4()}.js"
        with open(k6_output, "w") as f:
            f.write("// Dummy K6 script")
        output_paths.append(k6_output)

    os.remove(temp_file_name)

    return templates.TemplateResponse("csv_to_jmx.html", {
        "request": request,
        "output_paths": output_paths
    })


# --- Postman Collection to JMX UI and API ---

@app.get("/postman-to-jmx", response_class=HTMLResponse)
async def postman_form(request: Request):
    return templates.TemplateResponse("upload_postman.html", {"request": request})

@app.post("/generate-jmx")
async def generate_postman_jmx(request: Request, collection_file: UploadFile = File(...)):
    temp_dir = f"static/outputs/postman_{uuid.uuid4()}"
    os.makedirs(temp_dir, exist_ok=True)

    file_path = os.path.join(temp_dir, collection_file.filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(collection_file.file, f)

    from .utils.postman_parser import parse_postman_collection  # Adjust path if needed

    parsed_data = parse_postman_collection(file_path)

    def generate_jmx_script(grouped_requests, output_path):
        from xml.sax.saxutils import escape

        group_blocks = []
        for group_name, requests in grouped_requests.items():
            group_name_escaped = escape(group_name)
            samplers_block = ""
            for req in requests:
                # Ensure Content-Type header is present for body-based requests
                method = req['method']
                if method.upper() in ["POST", "PUT", "PATCH"] and req.get("body"):
                    header_keys = [h["key"].lower() for h in req.get("headers", [])]
                    if "content-type" not in header_keys:
                        req.setdefault("headers", []).append({
                            "key": "Content-Type",
                            "value": "application/json"
                        })

                headers_string = ""
                for header in req.get("headers", []):
                    key = escape(header['key'])
                    value = escape(header['value'])
                    headers_string += f"<elementProp name=\"{key}\" elementType=\"Header\">\n"
                    headers_string += f"  <stringProp name=\"Header.name\">{key}</stringProp>\n"
                    headers_string += f"  <stringProp name=\"Header.value\">{value}</stringProp>\n"
                    headers_string += "</elementProp>\n"

                name = escape(req['name'])
                path = escape(req['url'])
                method = escape(req['method'])

                body_string = ""
                post_body_block = ""
                if method.upper() in ["POST", "PUT", "PATCH"] and req.get("body"):
                    body_escaped = escape(req["body"])
                    post_body_block = f"""
  <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
  <elementProp name="HTTPsampler.Arguments" elementType="Arguments">
    <collectionProp name="Arguments.arguments">
      <elementProp name="" elementType="HTTPArgument">
        <boolProp name="HTTPArgument.always_encode">false</boolProp>
        <stringProp name="Argument.value">{body_escaped}</stringProp>
        <stringProp name="Argument.metadata">=</stringProp>
      </elementProp>
    </collectionProp>
  </elementProp>"""
                else:
                    post_body_block = """
  <elementProp name="HTTPsampler.Arguments" elementType="Arguments">
    <collectionProp name="Arguments.arguments"/>
  </elementProp>"""

                sampler = f"""
<HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="{name}" enabled="true">
  {post_body_block}
  <stringProp name="HTTPSampler.domain"></stringProp>
  <stringProp name="HTTPSampler.port"></stringProp>
  <stringProp name="HTTPSampler.protocol"></stringProp>
  <stringProp name="HTTPSampler.path">{path}</stringProp>
  <stringProp name="HTTPSampler.method">{method}</stringProp>
  <boolProp name="HTTPSampler.follow_redirects">true</boolProp>
  <boolProp name="HTTPSampler.auto_redirects">false</boolProp>
  <boolProp name="HTTPSampler.use_keepalive">true</boolProp>
  <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
  <stringProp name="HTTPSampler.embedded_url_re"></stringProp>
</HTTPSamplerProxy>
{f'''<hashTree>
  <HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="HTTP Header Manager" enabled="true">
    <collectionProp name="HeaderManager.headers">
      {headers_string}
    </collectionProp>
  </HeaderManager>
  <hashTree/>
</hashTree>''' if headers_string else '<hashTree/>'}
"""
                samplers_block += sampler

            group_block = f"""
<TransactionController guiclass="TransactionControllerGui" testclass="TransactionController" testname="{group_name_escaped}" enabled="true">
  <boolProp name="TransactionController.includeTimers">false</boolProp>
  <boolProp name="TransactionController.generateParentSample">false</boolProp>
</TransactionController>
<hashTree>
{samplers_block}
</hashTree>
"""
            group_blocks.append(group_block)

        env = Environment(loader=FileSystemLoader('templates'))
        template = env.get_template('postman.jmx.j2')
        rendered = template.render(transactions=group_blocks)
        with open(output_path, 'w') as f:
            f.write(rendered)

    jmx_output_path = os.path.join(temp_dir, "generated.jmx")
    generate_jmx_script(parsed_data["transactions"], jmx_output_path)


    # Render a result page with a download link and iframe to preview the JMX
    return templates.TemplateResponse("upload_postman.html", {
        "request": request,
        "output_path": "/" + jmx_output_path
    })


# --- Regex Generator UI and Logic ---

from .utils.regex_utils import build_regex_from_example

@app.get("/regex-generator", response_class=HTMLResponse)
async def show_regex_form(request: Request):
    """
    Serves the HTML form for regex generation from input/expected strings.
    """
    return templates.TemplateResponse("regex_generator.html", {"request": request})

@app.post("/generate-regex", response_class=HTMLResponse)
async def generate_regex(
    request: Request,
    input_str: str = Form(...),
    expected: str = Form(...)
):
    """
    Accepts input string and expected value to extract,
    then returns a regex pattern using the Jayanth-style boundary extractor.
    """
    result = build_regex_from_example(input_str, expected)
    return templates.TemplateResponse("regex_generator.html", {
        "request": request,
        "input_str": input_str,
        "expected": expected,
        "result": result
    })


# --- JMeter Execution and Results ---

@app.get("/execute", response_class=HTMLResponse)
async def get_execution_page(request: Request):
    return templates.TemplateResponse("execute.html", {"request": request})

@app.post("/run-jmeter")
async def run_jmeter_script(background_tasks: BackgroundTasks, jmx_file: UploadFile = File(...)):
    import datetime

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    api_name  = os.path.splitext(jmx_file.filename)[0]
    run_id    = f"{api_name}_{timestamp}"
    run_dir   = f"results/{run_id}"
    os.makedirs(run_dir, exist_ok=True)
    save_path = f"{run_dir}/{jmx_file.filename}"

    html_report_dir = os.path.join(run_dir, f"{api_name}_html_{timestamp}")
    os.makedirs(html_report_dir, exist_ok=True)

    with open(save_path, "wb") as f:
        f.write(await jmx_file.read())

    # Track current run for log access
    jmeter_status_tracker["current_run_id"] = run_id
    jmeter_status_tracker["current_run_dir"] = run_dir

    background_tasks.add_task(run_jmeter, save_path, run_dir, html_report_dir)
    return JSONResponse({
        "message": "Test started",
        "filename": jmx_file.filename,
        "run_id": run_id
    })

@app.get("/status")
def get_status():
    return {"status": jmeter_status_tracker.get("status", "Not Started")}

@app.get("/results", response_class=HTMLResponse)
def show_results(request: Request):
    import glob
    import os

    result_dirs = sorted(glob.glob("results/*"), key=os.path.getmtime, reverse=True)
    for dir_path in result_dirs:
        jtl_files = glob.glob(os.path.join(dir_path, "*.jtl"))
        if jtl_files:
            metrics = parse_jtl(jtl_files[0])
            return templates.TemplateResponse("results.html", {"request": request, "metrics": metrics})

    return templates.TemplateResponse("results.html", {"request": request, "metrics": []})


# --- Dashboard Route ---
from fastapi import Request
from fastapi.responses import HTMLResponse

@app.get("/dashboard", response_class=HTMLResponse)
async def show_dashboard(request: Request):
    return templates.TemplateResponse("dashboard.html", {"request": request})


# --- JMeter Log Route ---
@app.get("/jmeter-log")
async def get_jmeter_log():
    """
    Return the jmeter.log file from the current test run directory.
    Works on both Windows and Unix systems with proper path handling.
    """
    from fastapi.responses import HTMLResponse
    import os

    # Try to get current run directory from tracker
    current_run_dir = jmeter_status_tracker.get("current_run_dir")
    current_run_id = jmeter_status_tracker.get("current_run_id")
    
    if current_run_dir and current_run_id:
        # Use the tracked run directory with nested structure: results/{run_id}/{run_id}/jmeter.log
        log_path = os.path.join(current_run_dir, current_run_id, "jmeter.log")
    else:
        # Fallback: find the most recent test run directory
        results_dir = "results"
        if os.path.exists(results_dir):
            # Get all subdirectories in results folder
            run_dirs = [d for d in os.listdir(results_dir) 
                       if os.path.isdir(os.path.join(results_dir, d))]
            if run_dirs:
                # Sort by modification time (most recent first)
                run_dirs.sort(key=lambda x: os.path.getmtime(os.path.join(results_dir, x)), reverse=True)
                most_recent_run = run_dirs[0]
                # Use nested structure: results/{run_id}/{run_id}/jmeter.log
                log_path = os.path.join(results_dir, most_recent_run, most_recent_run, "jmeter.log")
            else:
                return HTMLResponse("No test runs found.", media_type="text/plain")
        else:
            return HTMLResponse("Results directory not found.", media_type="text/plain")
    
    # Check if log file exists and read it
    if os.path.exists(log_path):
        try:
            with open(log_path, "r", encoding="utf-8", errors="ignore") as f:
                content = f.read()
                return HTMLResponse(content, media_type="text/plain")
        except Exception as e:
            return HTMLResponse(f"Error reading log file: {str(e)}", media_type="text/plain")
    else:
        return HTMLResponse(f"Log file not found at: {log_path}", media_type="text/plain")


# --- Response‑time Summary Route ---
@app.get("/summary")
async def get_summary():
    """
    Return the newest JMeter statistics.json (HTML report) so the
    Execute page can render the response‑time table after a run.
    """
    import glob, os, json

    stats_files = sorted(
        glob.glob("results/**/statistics.json", recursive=True),
        key=os.path.getmtime,
        reverse=True
    )
    if stats_files:
        with open(stats_files[0], "r") as f:
            return json.load(f)
    return {}


# --- Download zipped result folder ---
@app.get("/download-results")
async def download_results(run_id: str):
    """
    Return a ZIP archive of the specified test run's results folder.
    Front‑end builds the URL as /download-results?run_id=<folder_name>.
    """
    import shutil, tempfile, os
    from fastapi.responses import FileResponse

    folder = os.path.join("results", run_id)
    if not os.path.isdir(folder):
        return JSONResponse({"error": "Run not found"}, status_code=404)

    # create temp ZIP
    tmp_base = tempfile.mktemp()
    zip_path = shutil.make_archive(tmp_base, 'zip', folder)
    return FileResponse(zip_path, filename=f"{run_id}.zip",
                        media_type="application/zip")
