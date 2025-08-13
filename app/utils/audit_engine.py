import asyncio
import datetime
import json
import os
import re
import shutil
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

# Optional dependencies (graceful degradation)
try:
	import httpx  # type: ignore
except ImportError:  # pragma: no cover
	httpx = None  # type: ignore

try:
	from bs4 import BeautifulSoup  # type: ignore
except ImportError:  # pragma: no cover
	BeautifulSoup = None  # type: ignore


# --- Configuration ---
@dataclass
class AuditConfig:
	target_url: str
	run_lighthouse: bool = True
	scan_security_headers: bool = True
	scan_js_vulns: bool = True
	run_ssl_scan: bool = False
	run_nuclei: bool = False
	# Auth for OWASP flows
	login_url: Optional[str] = None
	username_field: Optional[str] = None
	password_field: Optional[str] = None
	username: Optional[str] = None
	password: Optional[str] = None
	protected_url: Optional[str] = None
	# Crawl depth and limits
	max_pages: int = 50
	same_origin_only: bool = True


# --- Utilities ---
class ReportWriter:
	def __init__(self, report_root: str = "reports") -> None:
		self.report_root = report_root
		os.makedirs(self.report_root, exist_ok=True)

	def _timestamp_dir(self) -> str:
		stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
		out_dir = os.path.join(self.report_root, stamp)
		os.makedirs(out_dir, exist_ok=True)
		return out_dir

	def write(self, data: Dict, report_title: str = "Security & Performance Audit Report") -> Tuple[str, str]:
		out_dir = self._timestamp_dir()
		json_path = os.path.join(out_dir, "report.json")
		html_path = os.path.join(out_dir, "report.html")
		with open(json_path, "w", encoding="utf-8") as f:
			json.dump(data, f, indent=2)
		with open(html_path, "w", encoding="utf-8") as f:
			f.write(self._render_html(data, report_title))
		return json_path, html_path

	def _render_html(self, data: Dict, report_title: str) -> str:
		def section(title: str, body: str) -> str:
			return f"<section style='margin:16px;padding:16px;border:1px solid #334155;border-radius:12px;background:#0b1220;color:#e2e8f0'><h2 style='color:#22d3ee'>{title}</h2>{body}</section>"

		items = []
		items.append(section("Summary", f"<pre>{json.dumps(data.get('summary', {}), indent=2)}</pre>"))
		for key, value in data.items():
			if key == "summary":
				continue
			items.append(section(key.title(), f"<pre>{json.dumps(value, indent=2)}</pre>"))
		return """
		<!DOCTYPE html>
		<html><head><meta charset='utf-8'><title>%s</title>
		<link rel=\"preconnect\" href=\"https://fonts.googleapis.com\"><link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin>
		<link href=\"https://fonts.googleapis.com/css2?family=Inter:wght@400;600&display=swap\" rel=\"stylesheet\">
		</head>
		<body style='font-family:Inter,system-ui,Segoe UI,Arial,sans-serif;background:#020617;padding:24px;'>
		<h1 style='color:#e2e8f0'>%s</h1>
		%s
		</body></html>
		""" % (report_title, report_title, "\n".join(items))


# --- Crawler ---
class WebCrawler:
	def __init__(self, base_url: str, same_origin_only: bool = True, max_pages: int = 50) -> None:
		self.base_url = base_url.rstrip("/")
		self.same_origin_only = same_origin_only
		self.max_pages = max_pages

	def _same_origin(self, url: str) -> bool:
		from urllib.parse import urlparse
		b = urlparse(self.base_url)
		u = urlparse(url)
		return (b.scheme, b.netloc) == (u.scheme, u.netloc)

	async def crawl(self) -> List[str]:
		if httpx is None or BeautifulSoup is None:
			return [self.base_url]
		visited: Set[str] = set()
		queue: List[str] = [self.base_url]
		async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
			while queue and len(visited) < self.max_pages:
				url = queue.pop(0)
				if url in visited:
					continue
				try:
					resp = await client.get(url)
					visited.add(url)
					soup = BeautifulSoup(resp.text, "html.parser")  # type: ignore
					for a in soup.find_all("a", href=True):
						href = a["href"].strip()
						from urllib.parse import urljoin
						abs_url = urljoin(url, href)
						if self.same_origin_only and not self._same_origin(abs_url):
							continue
						if abs_url not in visited and abs_url not in queue:
							queue.append(abs_url)
				except Exception:
					visited.add(url)
		return list(visited)


# --- Scanner Interfaces ---
class Scanner(ABC):
	name: str

	@abstractmethod
	async def run(self, urls: List[str]) -> Dict:
		...


class LighthouseScanner(Scanner):
	name = "lighthouse"

	async def run(self, urls: List[str]) -> Dict:
		target = urls[0]
		result: Dict = {"available": False}
		if shutil.which("lighthouse") is None:
			result["note"] = "lighthouse CLI not found"
			return result
		# Run lighthouse with JSON output
		tmp_json = "lighthouse_report.json"
		cmd = [
			"lighthouse", target,
			"--quiet", "--chrome-flags=--headless",
			"--output=json", f"--output-path={tmp_json}",
		]
		try:
			proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
			_, stderr = await proc.communicate()
			if proc.returncode != 0:
				return {"available": True, "error": stderr.decode("utf-8", errors="ignore")}
			existing = {}
			if os.path.exists(tmp_json):
				with open(tmp_json, "r", encoding="utf-8") as f:
					existing = json.load(f)
				os.remove(tmp_json)
			cats = existing.get("categories", {})
			metrics = existing.get("audits", {})
			return {
				"available": True,
				"scores": {
					"performance": cats.get("performance", {}).get("score"),
					"accessibility": cats.get("accessibility", {}).get("score"),
					"best_practices": cats.get("best-practices", {}).get("score"),
					"seo": cats.get("seo", {}).get("score"),
				},
				"metrics": {
					"FCP": metrics.get("first-contentful-paint", {}).get("numericValue"),
					"LCP": metrics.get("largest-contentful-paint", {}).get("numericValue"),
					"TTI": metrics.get("interactive", {}).get("numericValue"),
					"TBT": metrics.get("total-blocking-time", {}).get("numericValue"),
					"CLS": metrics.get("cumulative-layout-shift", {}).get("numericValue"),
				},
			}
		except Exception as exc:
			return {"available": True, "error": str(exc)}


class SecurityHeadersScanner(Scanner):
	name = "security_headers"

	async def run(self, urls: List[str]) -> Dict:
		if httpx is None:
			return {"available": False, "note": "httpx not installed"}
		target = urls[0]
		async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:  # type: ignore
			resp = await client.get(target)
			headers = {k.lower(): v for k, v in resp.headers.items()}
			findings = []
			def missing(h: str, desc: str):
				if h not in headers:
					findings.append({"type": "missing_header", "header": h, "description": desc})
			missing("content-security-policy", "Missing Content Security Policy")
			missing("x-frame-options", "Lack of X-Frame-Options")
			missing("strict-transport-security", "No HSTS (Strict-Transport-Security)")
			missing("x-xss-protection", "Missing XSS protection header")
			missing("x-content-type-options", "Missing MIME sniffing protection header")
			cookie_flags: List[Dict] = []
			for cookie in resp.cookies.jar:
				cookie_flags.append({
					"name": cookie.name,
					"secure": cookie._rest.get("secure") is not None or getattr(cookie, "secure", False),
					"httponly": cookie._rest.get("httponly") is not None or cookie.has_nonstandard_attr("httponly"),
					"samesite": cookie._rest.get("samesite") or "",
				})
			return {"headers": headers, "findings": findings, "cookies": cookie_flags}


class JsVulnerabilityScanner(Scanner):
	name = "js_vulnerabilities"
	LIB_PATTERNS = [
		re.compile(r"/jquery[-.]([0-9.]+)\.js", re.I),
		re.compile(r"/bootstrap(?:\.bundle)?[-.]([0-9.]+)\.js", re.I),
		re.compile(r"/angular[-.]([0-9.]+)\.js", re.I),
		re.compile(r"/react[-.]([0-9.]+)\.js", re.I),
		re.compile(r"/vue[-.]([0-9.]+)\.js", re.I),
	]
	KNOWN_VULN: Dict[str, List[str]] = {
		"jquery": ["3.4.0", "1.12.4"],
		"bootstrap": ["4.3.1"],
		"angular": ["1.6.5"],
		"react": ["16.8.0"],
		"vue": ["2.5.16"],
	}

	async def run(self, urls: List[str]) -> Dict:
		if httpx is None or BeautifulSoup is None:
			return {"available": False, "note": "httpx/bs4 not installed"}
		async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:  # type: ignore
			results: Dict[str, List[Dict]] = {}
			for url in urls[:30]:
				try:
					resp = await client.get(url)
					soup = BeautifulSoup(resp.text, "html.parser")  # type: ignore
					libs: List[Dict] = []
					for s in soup.find_all("script", src=True):
						src = s["src"]
						for pat in self.LIB_PATTERNS:
							m = pat.search(src)
							if m:
								version = m.group(1)
								name = pat.pattern.split("/")[1].split("[")[0]
								vuln = version in self.KNOWN_VULN.get(name, [])
								libs.append({"name": name, "version": version, "potentially_vulnerable": vuln, "src": src})
						if libs:
							results[url] = libs
				except Exception:
					continue
			return results


class SslScanner(Scanner):
	name = "ssl_scan"

	async def run(self, urls: List[str]) -> Dict:
		from urllib.parse import urlparse
		target = urls[0]
		host = urlparse(target).netloc
		if shutil.which("sslscan") is None:
			return {"available": False, "note": "sslscan not installed"}
		cmd = ["sslscan", host]
		try:
			proc = await asyncio.create_subprocess_exec(*cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
			stdout, _ = await proc.communicate()
			return {"available": True, "output": stdout.decode("utf-8", errors="ignore")}
		except Exception as exc:
			return {"available": True, "error": str(exc)}


class NucleiScanner(Scanner):
	name = "nuclei"

	async def run(self, urls: List[str]) -> Dict:
		if shutil.which("nuclei") is None:
			return {"available": False, "note": "nuclei not installed"}
		try:
			proc = await asyncio.create_subprocess_exec(
				"nuclei", "-silent", "-json",
				stdin=asyncio.subprocess.PIPE,
				stdout=asyncio.subprocess.PIPE,
				stderr=asyncio.subprocess.PIPE,
			)
			stdin_data = ("\n".join(urls)).encode("utf-8")
			stdout, _ = await proc.communicate(stdin_data)
			lines = [json.loads(l) for l in stdout.decode("utf-8", errors="ignore").splitlines() if l.strip()]
			return {"available": True, "findings": lines}
		except Exception as exc:
			return {"available": True, "error": str(exc)}


# --- OWASP Auth Flow Checks ---
class AuthTester:
	async def login_and_fetch(
		self,
		login_url: str,
		username_field: str,
		password_field: str,
		username: str,
		password: str,
		protected_url: Optional[str],
	) -> Dict:
		if httpx is None or BeautifulSoup is None:
			return {"available": False, "note": "httpx/bs4 not installed"}
		results: Dict = {"login": {}, "protected": {}, "headers": {}, "csrf": {}, "rate_limit": {}, "injection": {}}
		jar = httpx.Cookies()  # type: ignore
		async with httpx.AsyncClient(follow_redirects=True, timeout=20, cookies=jar) as client:  # type: ignore
			# Pre-login protected check
			if protected_url:
				try:
					pre = await client.get(protected_url)
					results["protected"]["pre_login_status"] = pre.status_code
				except Exception:
					results["protected"]["pre_login_status"] = "error"
			# Fetch login page to look for CSRF token
			login_page = await client.get(login_url)
			soup = BeautifulSoup(login_page.text, "html.parser")  # type: ignore
			csrf_input = soup.find("input", attrs={"name": re.compile("csrf", re.I)})
			csrf_token = csrf_input["value"] if csrf_input and csrf_input.has_attr("value") else None
			form_data = {username_field: username, password_field: password}
			if csrf_token:
				form_data[csrf_input["name"]] = csrf_token
			# Submit login
			resp = await client.post(login_url, data=form_data)
			results["login"] = {"status_code": resp.status_code}
			# Session cookie checks
			cookie_flags: List[Dict] = []
			for cookie in client.cookies.jar:
				cookie_flags.append({
					"name": cookie.name,
					"secure": cookie._rest.get("secure") is not None or getattr(cookie, "secure", False),
					"httponly": cookie._rest.get("httponly") is not None or cookie.has_nonstandard_attr("httponly"),
					"samesite": cookie._rest.get("samesite") or "",
				})
			results["headers"]["cookies"] = cookie_flags
			# Access protected page
			if protected_url:
				prot = await client.get(protected_url)
				results["protected"]["post_login_status"] = prot.status_code
				headers = {k.lower(): v for k, v in prot.headers.items()}
				results["protected"]["headers"] = headers
			# Brute-force rate limit check: 5 rapid wrong attempts
			if username and password:
				for _ in range(5):
					await client.post(login_url, data={username_field: username, password_field: password + "_wrong"})
				final = await client.post(login_url, data={username_field: username, password_field: password + "_wrong"})
				results["rate_limit"] = {"status_code": final.status_code, "has_retry_after": "retry-after" in final.headers}
			# Simple injection probes on login
			payloads = {
				"xss": "<script>alert(1)</script>",
				"sql": "' OR '1'='1",
			}
			inj_res: Dict[str, Dict] = {}
			for k, v in payloads.items():
				r = await client.post(login_url, data={username_field: v, password_field: v})
				indicator = {
					"reflected": v in r.text[:5000],
					"status": r.status_code,
				}
				inj_res[k] = indicator
			results["injection"] = inj_res
		return results


# --- Orchestrator ---
class AuditEngine:
	def __init__(self, config: AuditConfig) -> None:
		self.config = config
		self.writer = ReportWriter()

	async def _collect_urls(self) -> List[str]:
		crawler = WebCrawler(self.config.target_url, same_origin_only=self.config.same_origin_only, max_pages=self.config.max_pages)
		urls = await crawler.crawl()
		if self.config.protected_url:
			urls.append(self.config.protected_url)
		return urls[: self.config.max_pages]

	async def run_performance_audit(self) -> Tuple[str, str]:
		urls = await self._collect_urls()
		tasks: List[Tuple[str, asyncio.Task]] = []
		if self.config.run_lighthouse:
			tasks.append(("lighthouse", asyncio.create_task(LighthouseScanner().run(urls))))
		if self.config.scan_js_vulns:
			tasks.append(("js_vulnerabilities", asyncio.create_task(JsVulnerabilityScanner().run(urls))))
		# Always include headers for best-practices
		tasks.append(("security_headers", asyncio.create_task(SecurityHeadersScanner().run(urls))))
		results: Dict[str, Dict] = {}
		for name, task in tasks:
			results[name] = await task
		summary = {
			"target": self.config.target_url,
			"pages_scanned": len(urls),
			"report_type": "performance",
		}
		data = {"summary": summary, **results}
		_, html_path = self.writer.write(data, report_title="Performance Audit Report")
		return html_path, json.dumps(summary, indent=2)

	async def run_security_audit(self) -> Tuple[str, str]:
		urls = await self._collect_urls()
		tasks: List[Tuple[str, asyncio.Task]] = []
		if self.config.scan_security_headers:
			tasks.append(("security_headers", asyncio.create_task(SecurityHeadersScanner().run(urls))))
		if self.config.scan_js_vulns:
			tasks.append(("js_vulnerabilities", asyncio.create_task(JsVulnerabilityScanner().run(urls))))
		if self.config.run_ssl_scan:
			tasks.append(("ssl_scan", asyncio.create_task(SslScanner().run(urls))))
		if self.config.run_nuclei:
			tasks.append(("nuclei", asyncio.create_task(NucleiScanner().run(urls))))
		# Optional auth flow
		auth_findings: Optional[Dict] = None
		if all([self.config.login_url, self.config.username_field, self.config.password_field, self.config.username, self.config.password]):
			auth_findings = await AuthTester().login_and_fetch(
				self.config.login_url, self.config.username_field, self.config.password_field,
				self.config.username, self.config.password, self.config.protected_url,
			)
		results: Dict[str, Dict] = {}
		for name, task in tasks:
			results[name] = await task
		if auth_findings is not None:
			results["auth_flow"] = auth_findings
		summary = {
			"target": self.config.target_url,
			"pages_scanned": len(urls),
			"checks": list(results.keys()) + (["auth_flow"] if auth_findings else []),
			"report_type": "security",
		}
		data = {"summary": summary, **results}
		_, html_path = self.writer.write(data, report_title="Security Audit Report")
		return html_path, json.dumps(summary, indent=2) 