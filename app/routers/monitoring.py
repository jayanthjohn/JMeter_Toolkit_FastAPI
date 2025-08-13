from fastapi import APIRouter, Request, Form
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from typing import Optional

from app.utils.audit_engine import AuditEngine, AuditConfig
from app.utils.system_monitor import run_system_monitor, get_system_snapshot


router = APIRouter(prefix="/monitoring", tags=["monitoring"])

templates = Jinja2Templates(directory="templates")


@router.get("/performance", response_class=HTMLResponse)
async def performance_page(request: Request):
	return templates.TemplateResponse("monitoring_performance.html", {"request": request, "report_preview": None, "report_link": None})


@router.post("/performance/run", response_class=HTMLResponse)
async def run_performance(request: Request,
	url: str = Form(...),
	lighthouse: Optional[str] = Form(None),
	headers: Optional[str] = Form(None),
	jsvuln: Optional[str] = Form(None),
	ssl: Optional[str] = Form(None),
	nuclei: Optional[str] = Form(None),
):
	config = AuditConfig(
		target_url=url,
		run_lighthouse=bool(lighthouse),
		scan_security_headers=bool(headers),
		scan_js_vulns=bool(jsvuln),
		run_ssl_scan=bool(ssl),
		run_nuclei=bool(nuclei),
	)
	engine = AuditEngine(config)
	report_path, preview = await engine.run_performance_audit()
	# Convert absolute/relative path to URL for mounted /reports
	rel = report_path.replace("\\", "/").split("reports/")[-1]
	report_url = f"/reports/{rel}"
	return templates.TemplateResponse("monitoring_performance.html", {"request": request, "report_preview": preview, "report_link": report_url})


@router.get("/security", response_class=HTMLResponse)
async def security_page(request: Request):
	return templates.TemplateResponse("monitoring_security.html", {"request": request, "report_preview": None, "report_link": None})


@router.post("/security/run", response_class=HTMLResponse)
async def run_security(request: Request,
	url: str = Form(...),
	headers: Optional[str] = Form(None),
	jsvuln: Optional[str] = Form(None),
	ssl: Optional[str] = Form(None),
	nuclei: Optional[str] = Form(None),
	login_url: Optional[str] = Form(None),
	username_field: Optional[str] = Form(None),
	password_field: Optional[str] = Form(None),
	username: Optional[str] = Form(None),
	password: Optional[str] = Form(None),
	protected_url: Optional[str] = Form(None),
):
	config = AuditConfig(
		target_url=url,
		scan_security_headers=bool(headers),
		scan_js_vulns=bool(jsvuln),
		run_ssl_scan=bool(ssl),
		run_nuclei=bool(nuclei),
		login_url=login_url,
		username_field=username_field,
		password_field=password_field,
		username=username,
		password=password,
		protected_url=protected_url,
	)
	engine = AuditEngine(config)
	report_path, preview = await engine.run_security_audit()
	rel = report_path.replace("\\", "/").split("reports/")[-1]
	report_url = f"/reports/{rel}"
	return templates.TemplateResponse("monitoring_security.html", {"request": request, "report_preview": preview, "report_link": report_url})


@router.get("/system", response_class=HTMLResponse)
async def system_page(request: Request):
	snapshot = get_system_snapshot()
	return templates.TemplateResponse("monitoring_system.html", {"request": request, "csv_link": None, "snapshot": snapshot})


@router.post("/system/run", response_class=HTMLResponse)
async def system_run(request: Request,
	interval: int = Form(...),
	duration: int = Form(...),
	label: Optional[str] = Form(None),
):
	csv_path = run_system_monitor(interval_seconds=int(interval), duration_seconds=int(duration), label=label or None)
	rel = csv_path.replace("\\", "/").split("reports/")[-1]
	csv_url = f"/reports/{rel}"
	snapshot = get_system_snapshot()
	return templates.TemplateResponse("monitoring_system.html", {"request": request, "csv_link": csv_url, "snapshot": snapshot})


@router.get("/system/snapshot")
async def system_snapshot():
	return get_system_snapshot() 