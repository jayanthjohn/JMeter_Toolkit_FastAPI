from fastapi import Request
from fastapi.responses import HTMLResponse

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from .routers import regex, scriptgen, chat

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

@app.get("/")
def read_root():
    return {"msg": "JMeter Toolkit FastAPI version running."}


# UI Home route
@app.get("/home", response_class=HTMLResponse)
def render_home(request: Request):
    return templates.TemplateResponse("base.html", {"request": request})


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
