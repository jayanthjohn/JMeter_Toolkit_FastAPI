from fastapi import APIRouter, Request, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader

from urllib.parse import urlsplit

# ---------- CSV helper to handle mixed‑case headers ----------
def csv_field(row: dict, *keys) -> str:
    """Return the first non‑empty value among the candidate header names."""
    row_lc = {k.lower(): (v or "").strip() for k, v in row.items()}
    for k in keys:
        if k.lower() in row_lc and row_lc[k.lower()]:
            return row_lc[k.lower()]
    return ""

import os, csv, uuid, shutil

router = APIRouter(prefix="/csv-to-jmx")
templates = Jinja2Templates(directory="templates")
templates.env.filters["basename"] = os.path.basename
env = Environment(loader=FileSystemLoader("templates"))

# -------------------------------------------------- UI page
@router.get("", response_class=HTMLResponse)
async def csv_to_jmx_page(request: Request):
    return templates.TemplateResponse("csv_to_jmx.html", {"request": request})

# -------------------------------------------------- template-based JMX builder
def generate_jmx_from_csv_using_template(csv_path: str, output_path: str):
    sampler_tmpl = env.get_template("http_request.xml.j2")
    plan_tmpl    = env.get_template("jmeter.jmx.j2")

    requests = []
    with open(csv_path, newline="") as fh:
        for row in csv.DictReader(fh):
            # ----- derive sampler fields using csv_field helper -----
            url = csv_field(row, "url")
            p   = urlsplit(url)

            requests.append({
                "name":   csv_field(row, "name", "api", "label", "endpoint") or "HTTP Request",
                "method": (csv_field(row, "method") or "GET").upper(),
                "scheme": p.scheme or "http",
                "domain": p.hostname or "",
                "port":   p.port or "",
                "path":   (p.path or "/") + ("?" + p.query if p.query else ""),
                "body":   csv_field(row, "body"),
                "headers": {
                    k.strip(): v.strip()
                    for kv in csv_field(row, "headers").split(";") if ":" in kv
                    for k, v in [kv.split(":", 1)]
                },
            })

    samplers = [sampler_tmpl.render(**r) for r in requests]
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(plan_tmpl.render(requests=samplers))

# -------------------------------------------------- main POST route
@router.post("/generate-scripts")
async def generate_scripts(
    request: Request,
    file: UploadFile = File(...),
    output_types: list[str] = Form(...)
):
    tmp_csv = f"tmp_{uuid.uuid4()}.csv"
    with open(tmp_csv, "wb") as buf:
        shutil.copyfileobj(file.file, buf)

    output_paths = []

    if "JMeter (.jmx)" in output_types:
        with open(tmp_csv, newline="") as fh:
            first = next(csv.DictReader(fh), {})
            raw   = csv_field(first, "name", "api", "label", "endpoint")
        safe = "".join(c if c.isalnum() or c in "-_" else "_" for c in (raw or ""))[:50] \
               or f"generated_{uuid.uuid4()}"
        jmx_path = f"static/outputs/{safe}.jmx"
        os.makedirs(os.path.dirname(jmx_path), exist_ok=True)
        generate_jmx_from_csv_using_template(tmp_csv, jmx_path)
        output_paths.append(jmx_path)

    if "K6 (.js)" in output_types:
        k6_path = f"static/outputs/{safe}.js"
        with open(k6_path, "w") as f:
            f.write("// TODO: real k6 script")
        output_paths.append(k6_path)

    os.remove(tmp_csv)

    return templates.TemplateResponse("csv_to_jmx.html",
        {"request": request, "output_paths": output_paths}
    )