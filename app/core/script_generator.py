import os
from urllib.parse import urlparse
import csv
import io
from jinja2 import Environment, FileSystemLoader
from urllib.parse import urlparse

# ------------------------------------------------------------------#
# Paths & Jinja setup
# ------------------------------------------------------------------#
BASE_DIR     = os.path.dirname(__file__)
TEMPLATE_DIR = os.path.join(BASE_DIR, "templates")
OUTPUT_DIR   = os.path.join("static", "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

env = Environment(loader=FileSystemLoader(TEMPLATE_DIR))

#-------------------------
#Enrich the CSV to JMX
#_______________________

def enrich_case(case: dict) -> dict:
    """Split case['url'] into scheme / domain / port / path for the template."""
    if "url" in case:
        p = urlparse(case["url"])
        case["scheme"]  = p.scheme or "https"
        case["domain"]  = p.hostname or ""
        case["port"]    = p.port
        case["path"]    = p.path or "/"
    return case
# ------------------------------------------------------------------#


# ------------------------------------------------------------------#
# Helpers
# ------------------------------------------------------------------#
def sanitize_filename(name: str) -> str:
    return name.replace(" ", "_").replace("/", "_")


# ------------------------------------------------------------------#
# CSV text -> JMX/K6 script generator
# ------------------------------------------------------------------#
def generate_script_from_csv(csv_text: str, mode: str = "jmeter") -> str:
    """
    Accepts raw CSV content as a string and returns generated JMX or K6 script path.
    CSV must have headers: name,url,method,body (optionally headers)
    """
    reader = csv.DictReader(io.StringIO(csv_text))
    cases = [row for row in reader if row.get("url") and row.get("name")]

    # Determine type
    if mode.lower() == "k6":
        output_types = ["K6 (.js)"]
    else:
        output_types = ["JMeter (.jmx)"]

    paths = generate_scripts(cases, output_types)
    return paths[0] if paths else "Error: No script generated"


# ------------------------------------------------------------------#
# 1. CSV  ->  JMX / K6  (unchanged)
# ------------------------------------------------------------------#
def generate_scripts(test_cases: list, output_types: list) -> list:
    """
    test_cases : list of dicts from CSV parser
    Each dict must have at least:
        name, method, scheme/domain/port/path OR url, body, headers …
    """
    output_paths = []
    sampler_tmpl = env.get_template("http_request.xml.j2")
    plan_tmpl    = env.get_template("jmeter.jmx.j2")
    k6_tmpl      = env.get_template("k6.js.j2")

    for raw in test_cases:
        case =enrich_case(raw.copy())
        fname = sanitize_filename(case["name"])

        # ---- JMeter (.jmx) -----------------------------------------
        if "JMeter (.jmx)" in output_types:
            #  render ONE sampler xml for this case
            sampler_xml = sampler_tmpl.render(**case)
            #  wrap it into a full plan
            plan_xml = plan_tmpl.render(requests=[sampler_xml])

            jmx_path = os.path.join(OUTPUT_DIR, f"{fname}.jmx")
            with open(jmx_path, "w", encoding="utf-8") as f:
                f.write(plan_xml)
            output_paths.append(jmx_path)

        # ---- K6 (.js) ----------------------------------------------
        if "K6 (.js)" in output_types:
            k6_path = os.path.join(OUTPUT_DIR, f"{fname}.js")
            with open(k6_path, "w", encoding="utf-8") as f:
                f.write(k6_tmpl.render(case))
            output_paths.append(k6_path)

    return output_paths

# ------------------------------------------------------------------#
# 2. HAR  ->  JMX
# ------------------------------------------------------------------#
def generate_jmx_from_har(requests: list,
                          output_name: str = "har_generated.jmx") -> str:
    """
    `requests` is a list of dictionaries containing:
    method, scheme, domain, port, path, body ...
    """
    # render each sampler independently
    sampler_tmpl = env.get_template("http_request.xml.j2")
    sampler_xml_list = [sampler_tmpl.render(**req) for req in requests]

    # wrap all samplers into full plan
    plan_tmpl = env.get_template("jmeter.jmx.j2")
    jmx_content = plan_tmpl.render(requests=sampler_xml_list)

    jmx_path = os.path.join(OUTPUT_DIR, output_name)
    with open(jmx_path, "w", encoding="utf-8") as f:
        f.write(jmx_content)

    return jmx_path


# ------------------------------------------------------------------#
# 3. (Optional) simple HAR parser if you need one here
# ------------------------------------------------------------------#
def parse_har(file_like) -> list:
    """
    Minimal HAR parser returning list[dict] ready for generate_jmx_from_har.
    """
    import json
    har = json.load(file_like)["log"]["entries"]
    requests = []
    for entry in har:
        r = entry["request"]
        p = urlparse(r["url"])
        requests.append(
            {
                "method":  r["method"],
                "scheme":  p.scheme,
                "domain":  p.hostname,
                "port":    p.port,
                "path":    p.path or "/",
                "body":    r.get("postData", {}).get("text", "")
            }
        )
    return requests

# ------------------------------------------------------------------#
#Post Man to JMX
# ------------------------------------------------------------------#

def generate_jmx_from_postman(transactions: list, output_name: str = "postman_generated.jmx") -> str:
    """
    transactions: [{ name: str, requests: [ request-dicts-compatible-with-sampler ] }]
    """
    sampler_tmpl = env.get_template("http_request.xml.j2")
    tx_tmpl      = env.get_template("transaction_block.xml.j2")
    plan_tmpl    = env.get_template("postman.jmx.j2")

    tx_blocks = []
    for tx in transactions:
        samplers_xml = []
        for req in tx["requests"]:
            samplers_xml.append(sampler_tmpl.render(**req))
        tx_xml = tx_tmpl.render(name=tx["name"], samplers_xml="".join(samplers_xml))
        tx_blocks.append(tx_xml)

    jmx_content = plan_tmpl.render(transactions=tx_blocks)

    out_path = os.path.join(OUTPUT_DIR, output_name)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(jmx_content)
    return out_path