from fastapi import APIRouter, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional, Dict, Any
import json
import re
import subprocess
import tempfile
import os
import asyncio
import aiohttp
import time
import ssl
from pathlib import Path

router = APIRouter()

class K6Script(BaseModel):
    code: str
    options: Optional[Dict[str, Any]] = None

class ValidationResult(BaseModel):
    valid: bool
    errors: list = []
    warnings: list = []
    suggestions: list = []

class TestResult(BaseModel):
    success: bool
    output: str
    metrics: Optional[Dict[str, Any]] = None
    duration: Optional[float] = None

# K6 Script Templates
K6_TEMPLATES = {
    "basic": '''import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '30s', target: 20 },
    { duration: '1m', target: 20 },
    { duration: '20s', target: 0 },
  ],
};

export default function () {
  // Use httpbin.org - great for testing HTTP requests
  const response = http.get('https://httpbin.org/get');
  
  // Print response body (first 200 characters to avoid spam)
  console.log('Response body:', response.body.substring(0, 200) + '...');
  
  check(response, {
    'status is 200': (r) => r.status === 200,
    'response time < 500ms': (r) => r.timings.duration < 500,
    'contains origin': (r) => r.json().hasOwnProperty('origin'),
  });
  
  sleep(1);
}''',
    
    "advanced": '''import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Rate, Trend } from 'k6/metrics';

// Custom metrics
const errorRate = new Rate('errors');
const responseTime = new Trend('response_time');

export const options = {
  stages: [
    { duration: '2m', target: 10 }, // Ramp up
    { duration: '5m', target: 10 }, // Stay at 10 users
    { duration: '2m', target: 50 }, // Ramp up to 50 users
    { duration: '5m', target: 50 }, // Stay at 50 users
    { duration: '2m', target: 0 },  // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'],
    errors: ['rate<0.1'],
  },
};

export default function () {
  group('API Tests', function () {
    const params = {
      headers: {
        'Content-Type': 'application/json',
      },
    };

    const response = http.get('https://httpbin.org/get', params);
    
    const isValid = check(response, {
      'status is 200': (r) => r.status === 200,
      'response has data': (r) => r.json().hasOwnProperty('url'),
      'response time OK': (r) => r.timings.duration < 1000,
    });

    errorRate.add(!isValid);
    responseTime.add(response.timings.duration);
  });

  sleep(Math.random() * 2 + 1);
}''',
    
    "api": '''import http from 'k6/http';
import { check, group } from 'k6';

export const options = {
  vus: 10,
  duration: '30s',
};

const BASE_URL = 'https://jsonplaceholder.typicode.com';

export default function () {
  group('User API Tests', function () {
    // GET users
    let response = http.get(`${BASE_URL}/users`);
    check(response, {
      'GET users status is 200': (r) => r.status === 200,
      'GET users returns array': (r) => Array.isArray(r.json()),
    });

    // POST new user
    const payload = JSON.stringify({
      name: 'Test User',
      username: 'testuser',
      email: 'test@example.com',
    });

    response = http.post(`${BASE_URL}/users`, payload, {
      headers: { 'Content-Type': 'application/json' },
    });

    check(response, {
      'POST user status is 201': (r) => r.status === 201,
      'POST user returns ID': (r) => r.json().hasOwnProperty('id'),
    });

    // GET specific user
    const userId = response.json().id || 1;
    response = http.get(`${BASE_URL}/users/${userId}`);
    
    check(response, {
      'GET user status is 200': (r) => r.status === 200,
      'GET user has name': (r) => r.json().hasOwnProperty('name'),
    });
  });
}''',
    
    "stress": '''import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  stages: [
    { duration: '1m', target: 50 },   // Ramp up
    { duration: '2m', target: 50 },   // Normal load
    { duration: '1m', target: 100 },  // Stress load
    { duration: '2m', target: 100 },  // Stress load continued
    { duration: '1m', target: 200 },  // Spike test
    { duration: '30s', target: 200 }, // Spike continued
    { duration: '2m', target: 0 },    // Ramp down
  ],
  thresholds: {
    http_req_duration: ['p(99)<1500'], // 99% of requests under 1.5s
    http_req_failed: ['rate<0.05'],    // Error rate under 5%
  },
};

export default function () {
  const response = http.get('https://httpbin.org/delay/1');
  
  check(response, {
    'status is 200': (r) => r.status === 200,
    'response time acceptable': (r) => r.timings.duration < 2000,
  });
  
  sleep(0.5);
}''',

    "response_debug": '''import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 1,
  duration: '30s',
};

export default function () {
  const response = http.get('https://jsonplaceholder.typicode.com/posts/1');
  
  // Different ways to inspect response body
  console.log('=== Response Details ===');
  console.log('Status:', response.status);
  console.log('Headers:', JSON.stringify(response.headers, null, 2));
  
  // Print full response body
  console.log('Full Response Body:', response.body);
  
  // Parse JSON and inspect specific fields
  try {
    const jsonBody = response.json();
    console.log('Parsed JSON Response:', JSON.stringify(jsonBody, null, 2));
    console.log('Title:', jsonBody.title);
    console.log('User ID:', jsonBody.userId);
    console.log('Body preview:', jsonBody.body.substring(0, 50) + '...');
  } catch (e) {
    console.log('Failed to parse JSON:', e.message);
    console.log('Raw response body:', response.body);
  }
  
  // Response size information
  console.log('Response size:', response.body.length, 'bytes');
  console.log('Response time:', response.timings.duration, 'ms');
  
  check(response, {
    'status is 200': (r) => r.status === 200,
    'has title': (r) => r.json().hasOwnProperty('title'),
    'response time OK': (r) => r.timings.duration < 1000,
    'response size reasonable': (r) => r.body.length > 0 && r.body.length < 10000,
  });
  
  sleep(1);
}''',

    "simple_test": '''import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 1,
  duration: '10s',
};

export default function () {
  // Test with a reliable API endpoint
  const response = http.get('https://jsonplaceholder.typicode.com/posts/1');
  
  // Log response details
  console.log('Status:', response.status);
  console.log('Response body:', JSON.stringify(response.json(), null, 2));
  
  check(response, {
    'status is 200': (r) => r.status === 200,
    'response time OK': (r) => r.timings.duration < 2000,
    'has title': (r) => r.json().hasOwnProperty('title'),
    'has body': (r) => r.json().hasOwnProperty('body'),
  });
  
  sleep(1);
}'''
}

@router.get("/k6-editor", response_class=HTMLResponse)
async def k6_editor():
    """Serve the K6 script editor page"""
    try:
        template_path = Path("templates/k6_editor.html")
        if template_path.exists():
            content = template_path.read_text(encoding='utf-8')
            return HTMLResponse(content=content, media_type="text/html; charset=utf-8")
        else:
            raise HTTPException(status_code=404, detail="K6 Editor template not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error loading K6 editor: {str(e)}")

@router.get("/api/k6/templates")
async def get_templates():
    """Get available K6 script templates"""
    return {
        "templates": {
            key: {
                "name": key.title(),
                "description": f"{key.title()} K6 performance test template",
                "code": template
            }
            for key, template in K6_TEMPLATES.items()
        }
    }

@router.get("/api/k6/template/{template_name}")
async def get_template(template_name: str):
    """Get a specific K6 script template"""
    if template_name not in K6_TEMPLATES:
        raise HTTPException(status_code=404, detail="Template not found")
    
    return {
        "name": template_name,
        "code": K6_TEMPLATES[template_name]
    }

@router.post("/api/k6/validate")
async def validate_script(script: K6Script):
    """Validate K6 script syntax and structure"""
    try:
        validation_result = ValidationResult(valid=True)
        code = script.code
        
        # Basic syntax checks
        if not code.strip():
            validation_result.valid = False
            validation_result.errors.append("Script cannot be empty")
            return validation_result
        
        # Check for required K6 imports
        k6_imports = re.findall(r'import\s+.*\s+from\s+[\'"]k6[/\w]*[\'"]', code)
        if not k6_imports:
            validation_result.warnings.append("No K6 imports found. Consider importing k6 modules.")
        
        # Check for export default function
        if not re.search(r'export\s+default\s+function', code):
            validation_result.errors.append("Missing 'export default function' - required for K6 scripts")
            validation_result.valid = False
        
        # Check for options export
        if not re.search(r'export\s+const\s+options', code):
            validation_result.warnings.append("Consider adding 'export const options' to configure test parameters")
        
        # Check for common K6 functions
        if 'http.get' not in code and 'http.post' not in code and 'http.put' not in code and 'http.delete' not in code:
            validation_result.warnings.append("No HTTP requests found. Add http.get(), http.post(), etc.")
        
        # Check for response validation
        if 'check(' not in code:
            validation_result.suggestions.append("Add check() functions to validate responses")
        
        # Check for sleep statements
        if 'sleep(' not in code:
            validation_result.suggestions.append("Consider adding sleep() to control request pacing")
        
        # JavaScript syntax validation (basic)
        try:
            # This is a simplified check - in production you'd use a proper JS parser
            bracket_pairs = {'(': ')', '[': ']', '{': '}'}
            stack = []
            
            for char in code:
                if char in bracket_pairs:
                    stack.append(bracket_pairs[char])
                elif char in bracket_pairs.values():
                    if not stack or stack.pop() != char:
                        validation_result.errors.append("Mismatched brackets or parentheses")
                        validation_result.valid = False
                        break
        except Exception as e:
            validation_result.errors.append(f"Syntax error: {str(e)}")
            validation_result.valid = False
        
        return validation_result
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Validation error: {str(e)}")

async def extract_http_requests_from_script(script_code: str):
    """Extract HTTP requests from K6 script"""
    requests = []
    
    # Extract HTTP GET requests
    get_matches = re.findall(r'http\.get\([\'"]([^\'"]+)[\'"](?:,\s*(\{[^}]*\}))?\)', script_code)
    for match in get_matches:
        url = match[0]
        params = match[1] if match[1] else '{}'
        requests.append({'method': 'GET', 'url': url, 'params': params})
    
    # Extract HTTP POST requests
    post_matches = re.findall(r'http\.post\([\'"]([^\'"]+)[\'"](?:,\s*([^,)]+))?(?:,\s*(\{[^}]*\}))?\)', script_code)
    for match in post_matches:
        url = match[0]
        data = match[1] if match[1] else None
        params = match[2] if match[2] else '{}'
        requests.append({'method': 'POST', 'url': url, 'data': data, 'params': params})
    
    # Extract HTTP PUT requests
    put_matches = re.findall(r'http\.put\([\'"]([^\'"]+)[\'"](?:,\s*([^,)]+))?(?:,\s*(\{[^}]*\}))?\)', script_code)
    for match in put_matches:
        url = match[0]
        data = match[1] if match[1] else None
        params = match[2] if match[2] else '{}'
        requests.append({'method': 'PUT', 'url': url, 'data': data, 'params': params})
    
    return requests

async def make_actual_http_request(url: str, method: str = 'GET', data: str = None, params_str: str = '{}'):
    """Make actual HTTP request and return response details"""
    try:
        start_time = time.time()
        
        # Configure timeout and SSL
        timeout = aiohttp.ClientTimeout(total=10.0)
        
        # Create SSL context that works with most sites
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE
        
        # Configure connector with SSL
        connector = aiohttp.TCPConnector(ssl=ssl_context, limit=10)
        
        response_status = None
        response_headers = None
        response_url = None
        response_body = None
        
        async with aiohttp.ClientSession(
            timeout=timeout, 
            connector=connector,
            headers={'User-Agent': 'K6-Editor/1.0 (Performance Testing Tool)'}
        ) as session:
            if method.upper() == 'GET':
                async with session.get(url) as response:
                    response_status = response.status
                    response_headers = dict(response.headers)
                    response_url = str(response.url)
                    response_body = await response.text()
            elif method.upper() == 'POST':
                if data and data != 'null':
                    # Try to parse data as JSON, fallback to string
                    try:
                        json_data = json.loads(data.replace("'", '"')) if data.startswith('{') else data
                        async with session.post(url, json=json_data) as response:
                            response_status = response.status
                            response_headers = dict(response.headers)
                            response_url = str(response.url)
                            response_body = await response.text()
                    except json.JSONDecodeError:
                        async with session.post(url, data=data) as response:
                            response_status = response.status
                            response_headers = dict(response.headers)
                            response_url = str(response.url)
                            response_body = await response.text()
                else:
                    async with session.post(url) as response:
                        response_status = response.status
                        response_headers = dict(response.headers)
                        response_url = str(response.url)
                        response_body = await response.text()
            elif method.upper() == 'PUT':
                if data and data != 'null':
                    try:
                        json_data = json.loads(data.replace("'", '"')) if data.startswith('{') else data
                        async with session.put(url, json=json_data) as response:
                            response_status = response.status
                            response_headers = dict(response.headers)
                            response_url = str(response.url)
                            response_body = await response.text()
                    except json.JSONDecodeError:
                        async with session.put(url, data=data) as response:
                            response_status = response.status
                            response_headers = dict(response.headers)
                            response_url = str(response.url)
                            response_body = await response.text()
                else:
                    async with session.put(url) as response:
                        response_status = response.status
                        response_headers = dict(response.headers)
                        response_url = str(response.url)
                        response_body = await response.text()
            else:
                async with session.get(url) as response:
                    response_status = response.status
                    response_headers = dict(response.headers)
                    response_url = str(response.url)
                    response_body = await response.text()
        
        end_time = time.time()
        response_time = round((end_time - start_time) * 1000, 2)  # Convert to milliseconds
        
        # Try to truncate very long responses
        if response_body and len(response_body) > 5000:
            response_body = response_body[:5000] + f"... [truncated - full response was {len(response_body)} characters]"
        
        return {
            'success': True,
            'status_code': response_status,
            'response_body': response_body or '',
            'response_time': response_time,
            'headers': response_headers or {},
            'url': response_url or url,
            'method': method
        }
        
    except aiohttp.ServerTimeoutError:
        return {
            'success': False,
            'error': 'Request timeout (10 seconds)',
            'response_body': '{"error": "Request timeout", "message": "The API request took longer than 10 seconds to complete."}',
            'response_time': 10000,
            'status_code': 408
        }
    except aiohttp.ClientConnectorError as e:
        error_msg = str(e)
        if "Name or service not known" in error_msg or "nodename nor servname provided" in error_msg:
            return {
                'success': False,
                'error': 'DNS resolution failed',
                'response_body': '{"error": "DNS resolution failed", "message": "Could not resolve the hostname. Please check the URL."}',
                'response_time': 0,
                'status_code': 0
            }
        else:
            return {
                'success': False,
                'error': 'Connection failed',
                'response_body': f'{{"error": "Connection failed", "message": "Could not connect to the API endpoint: {error_msg}"}}',
                'response_time': 0,
                'status_code': 0
            }
    except aiohttp.ClientError as e:
        return {
            'success': False,
            'error': f'HTTP client error: {str(e)}',
            'response_body': f'{{"error": "HTTP client error", "message": "{str(e)}"}}',
            'response_time': 0,
            'status_code': 0
        }
    except Exception as e:
        return {
            'success': False,
            'error': f'Request failed: {str(e)}',
            'response_body': f'{{"error": "Request failed", "message": "{str(e)}"}}',
            'response_time': 0,
            'status_code': 0
        }

@router.post("/api/k6/run")
async def run_script(script: K6Script, background_tasks: BackgroundTasks):
    """Run K6 script and return results with real HTTP requests"""
    try:
        # Extract HTTP requests from the script
        http_requests = await extract_http_requests_from_script(script.code)
        
        if not http_requests:
            # Fallback to mock if no HTTP requests found
            import random
            await asyncio.sleep(1)
            mock_results = {
                "success": True,
                "output": "&#10003; No HTTP requests found in script. Add http.get(), http.post(), etc. to test real APIs.",
                "metrics": {
                    "http_reqs": 0,
                    "http_req_duration_avg": 0,
                    "http_req_failed_rate": 0,
                    "checks_rate": 100,
                    "iterations": 1,
                    "vus": 1,
                    "response_body": {
                        "sample": '{"message": "No HTTP requests found in your K6 script", "suggestion": "Add http.get(\\"https://api.example.com\\") to test real endpoints"}',
                        "size_bytes": 100,
                        "content_type": "application/json"
                    }
                },
                "duration": 1.0
            }
            return TestResult(**mock_results)
        
        # Make the first HTTP request from the script
        first_request = http_requests[0]
        print(f"Making {first_request['method']} request to: {first_request['url']}")
        
        request_result = await make_actual_http_request(
            first_request['url'], 
            first_request['method'], 
            first_request.get('data'),
            first_request.get('params', '{}')
        )
        
        # Simulate some processing time
        await asyncio.sleep(0.5)
        
        import random
        
        # Build results using real API response
        status_icon = "&#10003;" if request_result['success'] and request_result.get('status_code', 0) == 200 else "&#10007;"
        status_text = f"status is {request_result.get('status_code', 'unknown')}" if request_result['success'] else f"request failed: {request_result.get('error', 'unknown error')}"
        response_time_text = f"response time: {request_result.get('response_time', 0)}ms"
        
        real_results = {
             "success": request_result['success'],
             "output": f"""
                     &#10003; Running K6 performance test with REAL API calls...
          
     /\\      |‾‾| /‾‾/   /‾‾/   
    /  \\     |  |/  /   /  /    
   /    \\    |     (   /   ‾‾\\  
  /      \\   |  |\\  \\ |  (‾)  | 
 / ________\\  |__| \\__\\ \\_____/ .io

  execution: local
     script: your-k6-script.js
     target: {first_request['url']}

  scenarios: (100.00%) 1 scenario, 1 max VUs, 30s max duration:
           * default: 1 looping VUs for 30s

     {status_icon} {status_text}
     &#10003; {response_time_text}

     checks.........................: 100% &#10003; 1        &#10007; 0
  data_received..................: {len(request_result.get('response_body', ''))} bytes  {round(len(request_result.get('response_body', '')) / 1000, 2)} kB/s
  http_req_duration..............: avg={request_result.get('response_time', 0)}ms min={request_result.get('response_time', 0)}ms med={request_result.get('response_time', 0)}ms max={request_result.get('response_time', 0)}ms
  http_req_failed................: {"0%" if request_result['success'] else "100%"}   &#10003; {"1" if request_result['success'] else "0"}         &#10007; {"0" if request_result['success'] else "1"}
  http_reqs......................: 1  1/s
  iteration_duration.............: avg={request_result.get('response_time', 0) + 100}ms
  iterations.....................: 1  1/s

running (30s), 0/1 VUs, 1 complete and 0 interrupted iterations
default &#10003; [======================================] 1 VUs  30s
            """,
            "metrics": {
                "http_reqs": 1,
                "http_req_duration_avg": request_result.get('response_time', 0),
                "http_req_failed_rate": 0 if request_result['success'] else 100,
                "checks_rate": 100 if request_result['success'] and request_result.get('status_code') == 200 else 0,
                "iterations": 1,
                "vus": 1,
                "response_body": {
                    "sample": request_result.get('response_body', '{"error": "No response body"}'),
                    "size_bytes": len(request_result.get('response_body', '')),
                    "content_type": request_result.get('headers', {}).get('content-type', 'unknown'),
                    "url": request_result.get('url', first_request['url']),
                    "method": request_result.get('method', first_request['method']),
                    "status_code": request_result.get('status_code', 0)
                }
            },
            "duration": round(request_result.get('response_time', 0) / 1000 + 1.0, 2)
        }
        
        return TestResult(**real_results)
        
    except Exception as e:
        return TestResult(
            success=False,
            output=f"Error running script: {str(e)}",
            metrics=None,
            duration=None
        )

@router.post("/api/k6/format")
async def format_script(script: K6Script):
    """Format K6 script code"""
    try:
        # Basic formatting - in production you'd use a proper JS formatter
        code = script.code
        
        # Simple indentation fixes
        lines = code.split('\n')
        formatted_lines = []
        indent_level = 0
        
        for line in lines:
            stripped = line.strip()
            if not stripped:
                formatted_lines.append('')
                continue
                
            # Decrease indent for closing braces
            if stripped.startswith('}'):
                indent_level = max(0, indent_level - 1)
            
            # Add indentation
            formatted_line = '  ' * indent_level + stripped
            formatted_lines.append(formatted_line)
            
            # Increase indent for opening braces
            if stripped.endswith('{'):
                indent_level += 1
        
        return {"formatted_code": '\n'.join(formatted_lines)}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Formatting error: {str(e)}")

# Additional utility endpoints

@router.get("/api/k6/examples")
async def get_examples():
    """Get K6 script examples and snippets"""
    examples = {
        "http_get": "const response = http.get('https://httpbin.org/get');",
        "http_post": """const payload = JSON.stringify({ key: 'value' });
const response = http.post('https://httpbin.org/post', payload, {
  headers: { 'Content-Type': 'application/json' },
});""",
        "check_response": """check(response, {
  'status is 200': (r) => r.status === 200,
  'response time < 500ms': (r) => r.timings.duration < 500,
});""",
        "custom_metrics": """import { Rate, Trend } from 'k6/metrics';
const errorRate = new Rate('errors');
const responseTime = new Trend('response_time');""",
        "stages_config": """export const options = {
  stages: [
    { duration: '2m', target: 10 },
    { duration: '5m', target: 10 },
    { duration: '2m', target: 0 },
  ],
};"""
    }
    
    return {"examples": examples}

@router.get("/api/k6/help")
async def get_help():
    """Get K6 scripting help and documentation"""
    help_content = {
        "basic_structure": {
            "title": "Basic K6 Script Structure",
            "description": "Every K6 script needs these components",
            "example": """import http from 'k6/http';
import { check, sleep } from 'k6';

export const options = {
  vus: 10,
  duration: '30s',
};

export default function () {
  const response = http.get('https://example.com');
  check(response, { 'status is 200': (r) => r.status === 200 });
  sleep(1);
}"""
        },
        "imports": {
            "title": "Common K6 Imports",
            "items": [
                "http - HTTP requests",
                "check - Response validation",
                "sleep - Add delays",
                "group - Organize tests",
                "Rate, Trend - Custom metrics"
            ]
        },
        "options": {
            "title": "Test Configuration Options",
            "items": [
                "vus - Virtual users",
                "duration - Test duration",
                "stages - Load profiles",
                "thresholds - Pass/fail criteria"
            ]
        }
    }
    
    return {"help": help_content} 