from fastapi import APIRouter, Request, HTTPException, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from typing import List, Dict, Any, Optional, Union
import json
import uuid
import os
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape, unescape
from jinja2 import Environment, FileSystemLoader

router = APIRouter()
templates = Jinja2Templates(directory="templates")

# JMX Component Models
class JMXComponent(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: str
    name: str
    enabled: bool = True
    position: Dict[str, float] = Field(default_factory=dict)
    properties: Dict[str, Any] = Field(default_factory=dict)
    children: List[str] = Field(default_factory=list)
    parent: Optional[str] = None

class JMXTestPlan(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Test Plan"
    components: Dict[str, JMXComponent] = Field(default_factory=dict)
    root_components: List[str] = Field(default_factory=list)

# JMX Component Library
JMX_COMPONENT_LIBRARY = {
    "test_plan": {
        "name": "Test Plan",
        "category": "root",
        "icon": "📋",
        "description": "Root container for all test elements",
        "properties": {
            "name": {"type": "string", "default": "Test Plan", "required": True},
            "comments": {"type": "textarea", "default": ""},
            "functional_mode": {"type": "boolean", "default": False},
            "teardown_on_shutdown": {"type": "boolean", "default": True},
            "serialize_threadgroups": {"type": "boolean", "default": False}
        },
        "allowed_children": ["thread_group", "config_element", "listener"]
    },
    "thread_group": {
        "name": "Thread Group",
        "category": "threads",
        "icon": "👥",
        "description": "Defines the number of users and ramp-up period",
        "properties": {
            "name": {"type": "string", "default": "Thread Group", "required": True},
            "num_threads": {"type": "number", "default": 1, "min": 1, "max": 10000},
            "ramp_time": {"type": "number", "default": 1, "min": 0},
            "loops": {"type": "number", "default": 1, "min": -1},
            "continue_forever": {"type": "boolean", "default": False},
            "on_sample_error": {"type": "select", "default": "continue", "options": ["continue", "startnextloop", "stopthread", "stoptest", "stoptestnow"]},
            "scheduler": {"type": "boolean", "default": False},
            "duration": {"type": "number", "default": 0, "min": 0},
            "delay": {"type": "number", "default": 0, "min": 0}
        },
        "allowed_children": ["sampler", "controller", "config_element", "listener", "timer", "assertion"]
    },
    "http_request": {
        "name": "HTTP Request",
        "category": "sampler",
        "icon": "🌐",
        "description": "Sends HTTP requests to web servers",
        "properties": {
            "name": {"type": "string", "default": "HTTP Request", "required": True},
            "domain": {"type": "string", "default": "", "placeholder": "example.com"},
            "port": {"type": "number", "default": "", "min": 1, "max": 65535},
            "protocol": {"type": "select", "default": "https", "options": ["http", "https"]},
            "path": {"type": "string", "default": "/", "placeholder": "/api/endpoint"},
            "method": {"type": "select", "default": "GET", "options": ["GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS"]},
            "follow_redirects": {"type": "boolean", "default": True},
            "auto_redirects": {"type": "boolean", "default": False},
            "use_keepalive": {"type": "boolean", "default": True},
            "body": {"type": "textarea", "default": "", "placeholder": "Request body (JSON, XML, etc.)"},
            "content_encoding": {"type": "string", "default": ""},
            "connect_timeout": {"type": "number", "default": "", "min": 0},
            "response_timeout": {"type": "number", "default": "", "min": 0}
        },
        "allowed_children": ["config_element", "assertion", "extractor"]
    },
    "transaction_controller": {
        "name": "Transaction Controller",
        "category": "controller",
        "icon": "📦",
        "description": "Groups samplers into transactions",
        "properties": {
            "name": {"type": "string", "default": "Transaction Controller", "required": True},
            "include_timers": {"type": "boolean", "default": True},
            "generate_parent_sample": {"type": "boolean", "default": False}
        },
        "allowed_children": ["sampler", "controller", "config_element", "timer", "assertion"]
    },
    "header_manager": {
        "name": "HTTP Header Manager",
        "category": "config_element",
        "icon": "📋",
        "description": "Manages HTTP headers for requests",
        "properties": {
            "name": {"type": "string", "default": "HTTP Header Manager", "required": True},
            "headers": {"type": "key_value_list", "default": []}
        },
        "allowed_children": []
    },
    "csv_data_config": {
        "name": "CSV Data Set Config",
        "category": "config_element", 
        "icon": "📊",
        "description": "Reads data from CSV files",
        "properties": {
            "name": {"type": "string", "default": "CSV Data Set Config", "required": True},
            "filename": {"type": "string", "default": "", "required": True},
            "variable_names": {"type": "string", "default": "", "placeholder": "var1,var2,var3"},
            "delimiter": {"type": "string", "default": ","},
            "allow_quoted_data": {"type": "boolean", "default": False},
            "recycle_on_eof": {"type": "boolean", "default": True},
            "stop_thread_on_eof": {"type": "boolean", "default": False},
            "sharing_mode": {"type": "select", "default": "shareMode.all", "options": ["shareMode.all", "shareMode.group", "shareMode.thread"]}
        },
        "allowed_children": []
    },
    "view_results_tree": {
        "name": "View Results Tree",
        "category": "listener",
        "icon": "🌳",
        "description": "Displays request and response data",
        "properties": {
            "name": {"type": "string", "default": "View Results Tree", "required": True},
            "filename": {"type": "string", "default": ""},
            "error_logging": {"type": "boolean", "default": False},
            "success_only_logging": {"type": "boolean", "default": False}
        },
        "allowed_children": []
    },
    "summary_report": {
        "name": "Summary Report",
        "category": "listener",
        "icon": "📈",
        "description": "Displays summary statistics",
        "properties": {
            "name": {"type": "string", "default": "Summary Report", "required": True},
            "filename": {"type": "string", "default": ""}
        },
        "allowed_children": []
    },
    "response_assertion": {
        "name": "Response Assertion",
        "category": "assertion",
        "icon": "✅",
        "description": "Validates response content",
        "properties": {
            "name": {"type": "string", "default": "Response Assertion", "required": True},
            "test_field": {"type": "select", "default": "Assertion.response_data", "options": ["Assertion.response_data", "Assertion.response_code", "Assertion.response_message", "Assertion.response_headers"]},
            "pattern_matching": {"type": "select", "default": "Assertion.TEST_FIELD_CONTAINS", "options": ["Assertion.TEST_FIELD_CONTAINS", "Assertion.TEST_FIELD_MATCHES", "Assertion.TEST_FIELD_EQUALS", "Assertion.TEST_FIELD_SUBSTRING", "Assertion.TEST_FIELD_NOT_CONTAINS", "Assertion.TEST_FIELD_NOT_EQUALS"]},
            "patterns": {"type": "string_list", "default": []},
            "assume_success": {"type": "boolean", "default": False},
            "not": {"type": "boolean", "default": False}
        },
        "allowed_children": []
    },
    "constant_timer": {
        "name": "Constant Timer",
        "category": "timer",
        "icon": "⏱️",
        "description": "Adds a constant delay between requests",
        "properties": {
            "name": {"type": "string", "default": "Constant Timer", "required": True},
            "delay": {"type": "number", "default": 1000, "min": 0, "placeholder": "Delay in milliseconds"}
        },
        "allowed_children": []
    }
}

# API Endpoints

@router.get("/jmx-editor", response_class=HTMLResponse)
async def jmx_editor_page(request: Request):
    """Serve the visual JMX editor page"""
    return templates.TemplateResponse("jmx_editor.html", {"request": request})

@router.get("/api/jmx/component-library")
async def get_component_library():
    """Get the complete JMX component library"""
    return {"components": JMX_COMPONENT_LIBRARY}

@router.get("/api/jmx/component-library/{category}")
async def get_components_by_category(category: str):
    """Get JMX components filtered by category"""
    filtered = {k: v for k, v in JMX_COMPONENT_LIBRARY.items() if v["category"] == category}
    return {"components": filtered}

@router.post("/api/jmx/validate-component")
async def validate_component(component: JMXComponent):
    """Validate a JMX component configuration"""
    errors = []
    warnings = []
    
    # Check if component type exists
    if component.type not in JMX_COMPONENT_LIBRARY:
        errors.append(f"Unknown component type: {component.type}")
        return {"valid": False, "errors": errors, "warnings": warnings}
    
    component_def = JMX_COMPONENT_LIBRARY[component.type]
    
    # Validate required properties
    for prop_name, prop_def in component_def["properties"].items():
        if prop_def.get("required", False) and prop_name not in component.properties:
            errors.append(f"Missing required property: {prop_name}")
        elif prop_name in component.properties:
            value = component.properties[prop_name]
            # Type validation
            if prop_def["type"] == "number" and not isinstance(value, (int, float)):
                if value != "":  # Allow empty values
                    errors.append(f"Property '{prop_name}' must be a number")
            elif prop_def["type"] == "boolean" and not isinstance(value, bool):
                errors.append(f"Property '{prop_name}' must be a boolean")
            # Range validation
            if prop_def["type"] == "number" and isinstance(value, (int, float)):
                if "min" in prop_def and value < prop_def["min"]:
                    errors.append(f"Property '{prop_name}' must be >= {prop_def['min']}")
                if "max" in prop_def and value > prop_def["max"]:
                    errors.append(f"Property '{prop_name}' must be <= {prop_def['max']}")
    
    # Component-specific validations
    if component.type == "http_request":
        if not component.properties.get("domain") and not component.properties.get("path", "").startswith("http"):
            warnings.append("HTTP Request should have a domain or full URL in path")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }

@router.post("/api/jmx/validate-test-plan")
async def validate_test_plan(test_plan: JMXTestPlan):
    """Validate an entire JMX test plan"""
    errors = []
    warnings = []
    
    # Check for required components
    has_thread_group = any(comp.type == "thread_group" for comp in test_plan.components.values())
    if not has_thread_group:
        errors.append("Test plan must contain at least one Thread Group")
    
    # Validate each component
    for comp_id, component in test_plan.components.items():
        result = await validate_component(component)
        if not result["valid"]:
            for error in result["errors"]:
                errors.append(f"Component '{component.name}': {error}")
        for warning in result["warnings"]:
            warnings.append(f"Component '{component.name}': {warning}")
    
    # Check component hierarchy
    for comp_id, component in test_plan.components.items():
        if component.parent:
            parent = test_plan.components.get(component.parent)
            if not parent:
                errors.append(f"Component '{component.name}' has invalid parent reference")
            else:
                parent_def = JMX_COMPONENT_LIBRARY.get(parent.type, {})
                allowed_children = parent_def.get("allowed_children", [])
                component_def = JMX_COMPONENT_LIBRARY.get(component.type, {})
                component_category = component_def.get("category", "")
                
                if allowed_children and component_category not in allowed_children:
                    errors.append(f"Component '{component.name}' cannot be a child of '{parent.name}'")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }

@router.post("/api/jmx/generate")
async def generate_jmx(test_plan: JMXTestPlan):
    """Generate JMX XML from visual test plan"""
    try:
        # Validate test plan first
        validation = await validate_test_plan(test_plan)
        if not validation["valid"]:
            return JSONResponse(
                status_code=400,
                content={"error": "Test plan validation failed", "details": validation["errors"]}
            )
        
        # Generate JMX XML
        jmx_xml = _generate_jmx_xml(test_plan)
        
        # Save to file
        filename = f"{test_plan.name.replace(' ', '_')}_{uuid.uuid4().hex[:8]}.jmx"
        output_path = f"static/outputs/{filename}"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        
        with open(output_path, "w", encoding="utf-8") as f:
            f.write(jmx_xml)
        
        return {
            "success": True,
            "filename": filename,
            "path": output_path,
            "download_url": f"/static/outputs/{filename}",
            "warnings": validation["warnings"]
        }
        
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to generate JMX: {str(e)}"}
        )

@router.post("/api/jmx/parse")
async def parse_jmx_file(file: UploadFile = File(...)):
    """Parse existing JMX file into visual components"""
    try:
        if not file.filename.endswith('.jmx'):
            return JSONResponse(
                status_code=400,
                content={"error": "File must be a .jmx file"}
            )
        
        # Read file content
        content = await file.read()
        xml_content = content.decode('utf-8')
        
        # Parse JMX XML
        test_plan = parse_jmx_xml(xml_content)
        
        return {
            "success": True,
            "test_plan": test_plan,
            "message": f"Successfully parsed {file.filename}"
        }
        
    except ET.ParseError as e:
        return JSONResponse(
            status_code=400,
            content={"error": f"Invalid XML format: {str(e)}"}
        )
    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Failed to parse JMX file: {str(e)}"}
        )

@router.post("/api/jmx/load-sample")
async def load_sample_jmx():
    """Load a sample JMX test plan for demonstration"""
    sample_test_plan = {
        "id": generateId(),
        "name": "Sample Test Plan",
        "components": {},
        "root_components": []
    }
    
    # Create Test Plan
    test_plan_comp = {
        "id": "test_plan_1",
        "type": "test_plan",
        "name": "Sample Test Plan",
        "enabled": True,
        "position": {"x": 0, "y": 0},
        "properties": {
            "name": "Sample Test Plan",
            "comments": "This is a sample test plan created for demonstration",
            "functional_mode": False,
            "teardown_on_shutdown": True,
            "serialize_threadgroups": False
        },
        "children": ["thread_group_1"],
        "parent": None
    }
    
    # Create Thread Group
    thread_group_comp = {
        "id": "thread_group_1",
        "type": "thread_group",
        "name": "Sample Thread Group",
        "enabled": True,
        "position": {"x": 0, "y": 0},
        "properties": {
            "name": "Sample Thread Group",
            "num_threads": 10,
            "ramp_time": 30,
            "loops": 1,
            "continue_forever": False,
            "on_sample_error": "continue",
            "scheduler": False,
            "duration": 0,
            "delay": 0
        },
        "children": ["http_request_1", "header_manager_1", "view_results_tree_1"],
        "parent": "test_plan_1"
    }
    
    # Create HTTP Request
    http_request_comp = {
        "id": "http_request_1",
        "type": "http_request",
        "name": "Sample API Request",
        "enabled": True,
        "position": {"x": 0, "y": 0},
        "properties": {
            "name": "Sample API Request",
            "domain": "httpbin.org",
            "port": "",
            "protocol": "https",
            "path": "/get",
            "method": "GET",
            "follow_redirects": True,
            "auto_redirects": False,
            "use_keepalive": True,
            "body": "",
            "content_encoding": "",
            "connect_timeout": "",
            "response_timeout": ""
        },
        "children": [],
        "parent": "thread_group_1"
    }
    
    # Create Header Manager
    header_manager_comp = {
        "id": "header_manager_1",
        "type": "header_manager",
        "name": "HTTP Header Manager",
        "enabled": True,
        "position": {"x": 0, "y": 0},
        "properties": {
            "name": "HTTP Header Manager",
            "headers": [
                {"key": "Accept", "value": "application/json"},
                {"key": "User-Agent", "value": "JMeter-Toolkit/1.0"}
            ]
        },
        "children": [],
        "parent": "thread_group_1"
    }
    
    # Create View Results Tree
    view_results_comp = {
        "id": "view_results_tree_1",
        "type": "view_results_tree",
        "name": "View Results Tree",
        "enabled": True,
        "position": {"x": 0, "y": 0},
        "properties": {
            "name": "View Results Tree",
            "filename": "",
            "error_logging": False,
            "success_only_logging": False
        },
        "children": [],
        "parent": "thread_group_1"
    }
    
    # Add components to test plan
    sample_test_plan["components"] = {
        "test_plan_1": test_plan_comp,
        "thread_group_1": thread_group_comp,
        "http_request_1": http_request_comp,
        "header_manager_1": header_manager_comp,
        "view_results_tree_1": view_results_comp
    }
    sample_test_plan["root_components"] = ["test_plan_1"]
    
    return {
        "success": True,
        "test_plan": sample_test_plan,
        "message": "Sample test plan loaded successfully"
    }

def _generate_jmx_xml(test_plan: JMXTestPlan) -> str:
    """Generate JMX XML from test plan components"""
    
    def escape_xml(text):
        if text is None:
            return ""
        return escape(str(text))
    
    def generate_component_xml(component: JMXComponent, indent_level: int = 0) -> str:
        indent = "  " * indent_level
        props = component.properties
        
        if component.type == "test_plan":
            xml = f'''{indent}<TestPlan guiclass="TestPlanGui" testclass="TestPlan" testname="{escape_xml(props.get('name', 'Test Plan'))}" enabled="{str(component.enabled).lower()}">
{indent}  <stringProp name="TestPlan.comments">{escape_xml(props.get('comments', ''))}</stringProp>
{indent}  <boolProp name="TestPlan.functional_mode">{str(props.get('functional_mode', False)).lower()}</boolProp>
{indent}  <boolProp name="TestPlan.tearDown_on_shutdown">{str(props.get('teardown_on_shutdown', True)).lower()}</boolProp>
{indent}  <elementProp name="TestPlan.user_defined_variables" elementType="Arguments">
{indent}    <collectionProp name="Arguments.arguments"/>
{indent}  </elementProp>
{indent}  <stringProp name="TestPlan.serialize_threadgroups">{str(props.get('serialize_threadgroups', False)).lower()}</stringProp>
{indent}</TestPlan>'''
            
        elif component.type == "thread_group":
            xml = f'''{indent}<ThreadGroup guiclass="ThreadGroupGui" testclass="ThreadGroup" testname="{escape_xml(props.get('name', 'Thread Group'))}" enabled="{str(component.enabled).lower()}">
{indent}  <stringProp name="ThreadGroup.on_sample_error">{escape_xml(props.get('on_sample_error', 'continue'))}</stringProp>
{indent}  <elementProp name="ThreadGroup.main_controller" elementType="LoopController">
{indent}    <boolProp name="LoopController.continue_forever">{str(props.get('continue_forever', False)).lower()}</boolProp>
{indent}    <stringProp name="LoopController.loops">{escape_xml(props.get('loops', 1))}</stringProp>
{indent}  </elementProp>
{indent}  <stringProp name="ThreadGroup.num_threads">{escape_xml(props.get('num_threads', 1))}</stringProp>
{indent}  <stringProp name="ThreadGroup.ramp_time">{escape_xml(props.get('ramp_time', 1))}</stringProp>
{indent}  <boolProp name="ThreadGroup.scheduler">{str(props.get('scheduler', False)).lower()}</boolProp>
{indent}  <stringProp name="ThreadGroup.duration">{escape_xml(props.get('duration', ''))}</stringProp>
{indent}  <stringProp name="ThreadGroup.delay">{escape_xml(props.get('delay', ''))}</stringProp>
{indent}</ThreadGroup>'''
            
        elif component.type == "http_request":
            body_xml = ""
            if props.get('body'):
                body_xml = f'''
{indent}  <boolProp name="HTTPSampler.postBodyRaw">true</boolProp>
{indent}  <elementProp name="HTTPsampler.Arguments" elementType="Arguments">
{indent}    <collectionProp name="Arguments.arguments">
{indent}      <elementProp name="" elementType="HTTPArgument">
{indent}        <boolProp name="HTTPArgument.always_encode">false</boolProp>
{indent}        <stringProp name="Argument.value">{escape_xml(props.get('body', ''))}</stringProp>
{indent}        <stringProp name="Argument.metadata">=</stringProp>
{indent}      </elementProp>
{indent}    </collectionProp>
{indent}  </elementProp>'''
            else:
                body_xml = f'''
{indent}  <elementProp name="HTTPsampler.Arguments" elementType="Arguments">
{indent}    <collectionProp name="Arguments.arguments"/>
{indent}  </elementProp>'''
            
            xml = f'''{indent}<HTTPSamplerProxy guiclass="HttpTestSampleGui" testclass="HTTPSamplerProxy" testname="{escape_xml(props.get('name', 'HTTP Request'))}" enabled="{str(component.enabled).lower()}">
{body_xml}
{indent}  <stringProp name="HTTPSampler.domain">{escape_xml(props.get('domain', ''))}</stringProp>
{indent}  <stringProp name="HTTPSampler.port">{escape_xml(props.get('port', ''))}</stringProp>
{indent}  <stringProp name="HTTPSampler.protocol">{escape_xml(props.get('protocol', 'https'))}</stringProp>
{indent}  <stringProp name="HTTPSampler.path">{escape_xml(props.get('path', '/'))}</stringProp>
{indent}  <stringProp name="HTTPSampler.method">{escape_xml(props.get('method', 'GET'))}</stringProp>
{indent}  <boolProp name="HTTPSampler.follow_redirects">{str(props.get('follow_redirects', True)).lower()}</boolProp>
{indent}  <boolProp name="HTTPSampler.auto_redirects">{str(props.get('auto_redirects', False)).lower()}</boolProp>
{indent}  <boolProp name="HTTPSampler.use_keepalive">{str(props.get('use_keepalive', True)).lower()}</boolProp>
{indent}  <boolProp name="HTTPSampler.DO_MULTIPART_POST">false</boolProp>
{indent}  <stringProp name="HTTPSampler.embedded_url_re"></stringProp>
{indent}  <stringProp name="HTTPSampler.connect_timeout">{escape_xml(props.get('connect_timeout', ''))}</stringProp>
{indent}  <stringProp name="HTTPSampler.response_timeout">{escape_xml(props.get('response_timeout', ''))}</stringProp>
{indent}</HTTPSamplerProxy>'''
            
        elif component.type == "transaction_controller":
            xml = f'''{indent}<TransactionController guiclass="TransactionControllerGui" testclass="TransactionController" testname="{escape_xml(props.get('name', 'Transaction Controller'))}" enabled="{str(component.enabled).lower()}">
{indent}  <boolProp name="TransactionController.includeTimers">{str(props.get('include_timers', True)).lower()}</boolProp>
{indent}  <boolProp name="TransactionController.generateParentSample">{str(props.get('generate_parent_sample', False)).lower()}</boolProp>
{indent}</TransactionController>'''
            
        elif component.type == "header_manager":
            headers_xml = ""
            for header in props.get('headers', []):
                if isinstance(header, dict) and 'key' in header and 'value' in header:
                    headers_xml += f'''
{indent}    <elementProp name="{escape_xml(header['key'])}" elementType="Header">
{indent}      <stringProp name="Header.name">{escape_xml(header['key'])}</stringProp>
{indent}      <stringProp name="Header.value">{escape_xml(header['value'])}</stringProp>
{indent}    </elementProp>'''
            
            xml = f'''{indent}<HeaderManager guiclass="HeaderPanel" testclass="HeaderManager" testname="{escape_xml(props.get('name', 'HTTP Header Manager'))}" enabled="{str(component.enabled).lower()}">
{indent}  <collectionProp name="HeaderManager.headers">{headers_xml}
{indent}  </collectionProp>
{indent}</HeaderManager>'''
            
        elif component.type == "view_results_tree":
            xml = f'''{indent}<ResultCollector guiclass="ViewResultsFullVisualizer" testclass="ResultCollector" testname="{escape_xml(props.get('name', 'View Results Tree'))}" enabled="{str(component.enabled).lower()}">
{indent}  <boolProp name="ResultCollector.error_logging">{str(props.get('error_logging', False)).lower()}</boolProp>
{indent}  <objProp>
{indent}    <name>saveConfig</name>
{indent}    <value class="SampleSaveConfiguration">
{indent}      <time>true</time>
{indent}      <latency>true</latency>
{indent}      <timestamp>true</timestamp>
{indent}      <success>true</success>
{indent}      <label>true</label>
{indent}      <code>true</code>
{indent}      <message>true</message>
{indent}      <threadName>true</threadName>
{indent}      <dataType>true</dataType>
{indent}      <encoding>false</encoding>
{indent}      <assertions>true</assertions>
{indent}      <subresults>true</subresults>
{indent}      <responseData>false</responseData>
{indent}      <samplerData>false</samplerData>
{indent}      <xml>false</xml>
{indent}      <fieldNames>true</fieldNames>
{indent}      <responseHeaders>false</responseHeaders>
{indent}      <requestHeaders>false</requestHeaders>
{indent}      <responseDataOnError>false</responseDataOnError>
{indent}      <saveAssertionResultsFailureMessage>true</saveAssertionResultsFailureMessage>
{indent}      <assertionsResultsToSave>0</assertionsResultsToSave>
{indent}      <bytes>true</bytes>
{indent}      <sentBytes>true</sentBytes>
{indent}      <url>true</url>
{indent}      <threadCounts>true</threadCounts>
{indent}      <idleTime>true</idleTime>
{indent}      <connectTime>true</connectTime>
{indent}    </value>
{indent}  </objProp>
{indent}  <stringProp name="filename">{escape_xml(props.get('filename', ''))}</stringProp>
{indent}</ResultCollector>'''
            
        else:
            # Generic component fallback
            xml = f'{indent}<!-- Unsupported component type: {component.type} -->'
        
        return xml
    
    def build_hierarchy(components_dict: Dict[str, JMXComponent], root_ids: List[str], indent_level: int = 1) -> str:
        result = ""
        indent = "  " * indent_level
        
        for comp_id in root_ids:
            if comp_id not in components_dict:
                continue
                
            component = components_dict[comp_id]
            result += generate_component_xml(component, indent_level) + "\n"
            
            # Add hashTree for children
            if component.children:
                result += f"{indent}<hashTree>\n"
                result += build_hierarchy(components_dict, component.children, indent_level + 1)
                result += f"{indent}</hashTree>\n"
            else:
                result += f"{indent}<hashTree/>\n"
        
        return result
    
    # Start building the XML
    xml_header = '<?xml version="1.0" encoding="UTF-8"?>\n'
    xml_root_start = '<jmeterTestPlan version="1.2" properties="5.0" jmeter="5.6.3">\n  <hashTree>\n'
    
    # Build component hierarchy
    xml_body = build_hierarchy(test_plan.components, test_plan.root_components, 2)
    
    xml_root_end = '  </hashTree>\n</jmeterTestPlan>'
    
    return xml_header + xml_root_start + xml_body + xml_root_end

def generateId():
    """Generate a unique component ID"""
    return 'comp_' + str(uuid.uuid4()).replace('-', '')[:12]

def parse_jmx_xml(xml_content: str) -> Dict[str, Any]:
    """Parse JMX XML content and convert to visual test plan format"""
    try:
        root = ET.fromstring(xml_content)
        
        # Initialize test plan structure
        test_plan = {
            "id": generateId(),
            "name": "Imported Test Plan",
            "components": {},
            "root_components": []
        }
        
        # Parse the root hashTree which contains the TestPlan
        root_hash_tree = root.find('hashTree')
        if root_hash_tree is not None:
            parse_hash_tree(root_hash_tree, None, test_plan)
        
        return test_plan
        
    except Exception as e:
        raise Exception(f"Error parsing JMX XML: {str(e)}")

def parse_test_plan_element(elem) -> Dict[str, Any]:
    """Parse TestPlan XML element"""
    component = {
        "id": generateId(),
        "type": "test_plan",
        "name": elem.get("testname", "Test Plan"),
        "enabled": elem.get("enabled", "true").lower() == "true",
        "position": {"x": 0, "y": 0},
        "properties": {
            "name": elem.get("testname", "Test Plan"),
            "comments": get_string_prop(elem, "TestPlan.comments", ""),
            "functional_mode": get_bool_prop(elem, "TestPlan.functional_mode", False),
            "teardown_on_shutdown": get_bool_prop(elem, "TestPlan.tearDown_on_shutdown", True),
            "serialize_threadgroups": get_bool_prop(elem, "TestPlan.serialize_threadgroups", False)
        },
        "children": [],
        "parent": None
    }
    return component

def parse_thread_group_element(elem) -> Dict[str, Any]:
    """Parse ThreadGroup XML element"""
    # Extract loop controller properties
    loop_controller = elem.find('.//elementProp[@elementType="LoopController"]')
    loops = "1"
    continue_forever = False
    
    if loop_controller is not None:
        loops = get_string_prop(loop_controller, "LoopController.loops", "1")
        continue_forever = get_bool_prop(loop_controller, "LoopController.continue_forever", False)
    
    # Handle numeric conversion safely
    try:
        num_threads = int(get_string_prop(elem, "ThreadGroup.num_threads", "1"))
    except (ValueError, TypeError):
        num_threads = 1
        
    try:
        ramp_time = int(get_string_prop(elem, "ThreadGroup.ramp_time", "1"))
    except (ValueError, TypeError):
        ramp_time = 1
        
    try:
        loops_int = int(loops) if loops and loops != "" else 1
    except (ValueError, TypeError):
        loops_int = 1
    
    component = {
        "id": generateId(),
        "type": "thread_group",
        "name": elem.get("testname", "Thread Group"),
        "enabled": elem.get("enabled", "true").lower() == "true",
        "position": {"x": 0, "y": 0},
        "properties": {
            "name": elem.get("testname", "Thread Group"),
            "num_threads": num_threads,
            "ramp_time": ramp_time,
            "loops": loops_int,
            "continue_forever": continue_forever,
            "on_sample_error": get_string_prop(elem, "ThreadGroup.on_sample_error", "continue"),
            "scheduler": get_bool_prop(elem, "ThreadGroup.scheduler", False),
            "duration": get_string_prop(elem, "ThreadGroup.duration", ""),
            "delay": get_string_prop(elem, "ThreadGroup.delay", "")
        },
        "children": [],
        "parent": None
    }
    return component

def parse_http_sampler_element(elem) -> Dict[str, Any]:
    """Parse HTTPSamplerProxy XML element"""
    # Handle port conversion safely
    port_str = get_string_prop(elem, "HTTPSampler.port", "")
    port_value = ""
    if port_str and port_str.strip():
        try:
            # Validate port is numeric and in valid range
            port_num = int(port_str)
            if 1 <= port_num <= 65535:
                port_value = port_num
            else:
                port_value = ""
        except (ValueError, TypeError):
            port_value = ""
    
    component = {
        "id": generateId(),
        "type": "http_request",
        "name": elem.get("testname", "HTTP Request"),
        "enabled": elem.get("enabled", "true").lower() == "true",
        "position": {"x": 0, "y": 0},
        "properties": {
            "name": elem.get("testname", "HTTP Request"),
            "domain": get_string_prop(elem, "HTTPSampler.domain", ""),
            "port": port_value,
            "protocol": get_string_prop(elem, "HTTPSampler.protocol", "https"),
            "path": get_string_prop(elem, "HTTPSampler.path", "/"),
            "method": get_string_prop(elem, "HTTPSampler.method", "GET"),
            "follow_redirects": get_bool_prop(elem, "HTTPSampler.follow_redirects", True),
            "auto_redirects": get_bool_prop(elem, "HTTPSampler.auto_redirects", False),
            "use_keepalive": get_bool_prop(elem, "HTTPSampler.use_keepalive", True),
            "body": extract_http_body(elem),
            "content_encoding": get_string_prop(elem, "HTTPSampler.contentEncoding", ""),
            "connect_timeout": get_string_prop(elem, "HTTPSampler.connect_timeout", ""),
            "response_timeout": get_string_prop(elem, "HTTPSampler.response_timeout", "")
        },
        "children": [],
        "parent": None
    }
    return component

def parse_transaction_controller_element(elem) -> Dict[str, Any]:
    """Parse TransactionController XML element"""
    component = {
        "id": generateId(),
        "type": "transaction_controller",
        "name": elem.get("testname", "Transaction Controller"),
        "enabled": elem.get("enabled", "true").lower() == "true",
        "position": {"x": 0, "y": 0},
        "properties": {
            "name": elem.get("testname", "Transaction Controller"),
            "include_timers": get_bool_prop(elem, "TransactionController.includeTimers", True),
            "generate_parent_sample": get_bool_prop(elem, "TransactionController.generateParentSample", False)
        },
        "children": [],
        "parent": None
    }
    return component

def parse_header_manager_element(elem) -> Dict[str, Any]:
    """Parse HeaderManager XML element"""
    headers = []
    header_collection = elem.find('.//collectionProp[@name="HeaderManager.headers"]')
    if header_collection is not None:
        for header_elem in header_collection.findall('elementProp'):
            key = get_string_prop(header_elem, "Header.name", "")
            value = get_string_prop(header_elem, "Header.value", "")
            if key:
                headers.append({"key": key, "value": value})
    
    component = {
        "id": generateId(),
        "type": "header_manager",
        "name": elem.get("testname", "HTTP Header Manager"),
        "enabled": elem.get("enabled", "true").lower() == "true",
        "position": {"x": 0, "y": 0},
        "properties": {
            "name": elem.get("testname", "HTTP Header Manager"),
            "headers": headers
        },
        "children": [],
        "parent": None
    }
    return component

def parse_result_collector_element(elem) -> Dict[str, Any]:
    """Parse ResultCollector XML element (listeners)"""
    gui_class = elem.get("guiclass", "")
    
    if "ViewResultsFullVisualizer" in gui_class:
        component_type = "view_results_tree"
        name = elem.get("testname", "View Results Tree")
    elif "SummaryReport" in gui_class:
        component_type = "summary_report"
        name = elem.get("testname", "Summary Report")
    else:
        component_type = "view_results_tree"  # Default fallback
        name = elem.get("testname", "Listener")
    
    component = {
        "id": generateId(),
        "type": component_type,
        "name": name,
        "enabled": elem.get("enabled", "true").lower() == "true",
        "position": {"x": 0, "y": 0},
        "properties": {
            "name": name,
            "filename": get_string_prop(elem, "filename", ""),
            "error_logging": get_bool_prop(elem, "ResultCollector.error_logging", False),
            "success_only_logging": get_bool_prop(elem, "ResultCollector.success_only_logging", False)
        },
        "children": [],
        "parent": None
    }
    return component

def parse_hash_tree(hash_tree_elem, parent_id: Optional[str], test_plan: Dict[str, Any]):
    """Recursively parse hashTree elements and their children"""
    current_component = None
    
    for child in hash_tree_elem:
        if child.tag == "hashTree":
            # This is a nested hashTree - parse its children for the current component
            if current_component:
                parse_hash_tree(child, current_component["id"], test_plan)
        else:
            # This is a component element
            component = parse_component_element(child)
            if component:
                component["parent"] = parent_id
                test_plan["components"][component["id"]] = component
                
                # Add to parent's children or root components
                if parent_id and parent_id in test_plan["components"]:
                    test_plan["components"][parent_id]["children"].append(component["id"])
                elif parent_id is None:
                    # This is a root component
                    test_plan["root_components"].append(component["id"])
                    # Update test plan name if this is the TestPlan component
                    if component["type"] == "test_plan":
                        test_plan["name"] = component["name"]
                
                current_component = component

def parse_component_element(elem) -> Optional[Dict[str, Any]]:
    """Parse any JMX component element based on its testclass"""
    testclass = elem.get("testclass", "")
    
    try:
        if testclass == "TestPlan":
            return parse_test_plan_element(elem)
        elif testclass == "ThreadGroup":
            return parse_thread_group_element(elem)
        elif testclass == "HTTPSamplerProxy":
            return parse_http_sampler_element(elem)
        elif testclass == "TransactionController":
            return parse_transaction_controller_element(elem)
        elif testclass == "HeaderManager":
            return parse_header_manager_element(elem)
        elif testclass == "ResultCollector":
            return parse_result_collector_element(elem)
        elif testclass in ["ConstantTimer", "UniformRandomTimer", "GaussianRandomTimer"]:
            # Timer components
            delay_str = get_string_prop(elem, "ConstantTimer.delay", "1000")
            try:
                delay_value = int(delay_str) if delay_str else 1000
            except (ValueError, TypeError):
                delay_value = 1000
                
            return {
                "id": generateId(),
                "type": "constant_timer",
                "name": elem.get("testname", "Timer"),
                "enabled": elem.get("enabled", "true").lower() == "true",
                "position": {"x": 0, "y": 0},
                "properties": {
                    "name": elem.get("testname", "Timer"),
                    "delay": delay_value
                },
                "children": [],
                "parent": None
            }
        elif testclass in ["ResponseAssertion", "JSONPathAssertion", "XPathAssertion"]:
            # Assertion components
            return {
                "id": generateId(),
                "type": "response_assertion",
                "name": elem.get("testname", "Assertion"),
                "enabled": elem.get("enabled", "true").lower() == "true",
                "position": {"x": 0, "y": 0},
                "properties": {
                    "name": elem.get("testname", "Assertion"),
                    "test_field": get_string_prop(elem, "Assertion.test_field", "Assertion.response_data"),
                    "pattern_matching": get_string_prop(elem, "Assertion.assume_success", "Assertion.TEST_FIELD_CONTAINS"),
                    "patterns": [],
                    "assume_success": get_bool_prop(elem, "Assertion.assume_success", False),
                    "not": get_bool_prop(elem, "Assertion.negate", False)
                },
                "children": [],
                "parent": None
            }
        else:
            # Unknown component type - create a generic component
            return {
                "id": generateId(),
                "type": "unknown",
                "name": elem.get("testname", f"Unknown ({testclass})"),
                "enabled": elem.get("enabled", "true").lower() == "true",
                "position": {"x": 0, "y": 0},
                "properties": {"name": elem.get("testname", f"Unknown ({testclass})")},
                "children": [],
                "parent": None
            }
    except Exception as e:
        # If parsing fails, create a generic component with error info
        return {
            "id": generateId(),
            "type": "unknown",
            "name": elem.get("testname", f"Parse Error ({testclass})"),
            "enabled": elem.get("enabled", "true").lower() == "true",
            "position": {"x": 0, "y": 0},
            "properties": {
                "name": elem.get("testname", f"Parse Error ({testclass})"),
                "error": f"Failed to parse: {str(e)}"
            },
            "children": [],
            "parent": None
        }

def get_string_prop(elem, prop_name: str, default: str = "") -> str:
    """Extract string property from JMX element"""
    prop_elem = elem.find(f'.//stringProp[@name="{prop_name}"]')
    if prop_elem is not None and prop_elem.text:
        return unescape(prop_elem.text)
    return default

def get_bool_prop(elem, prop_name: str, default: bool = False) -> bool:
    """Extract boolean property from JMX element"""
    prop_elem = elem.find(f'.//boolProp[@name="{prop_name}"]')
    if prop_elem is not None and prop_elem.text:
        return prop_elem.text.lower() == "true"
    return default

def get_int_prop(elem, prop_name: str, default: int = 0) -> int:
    """Extract integer property from JMX element"""
    prop_elem = elem.find(f'.//intProp[@name="{prop_name}"]')
    if prop_elem is not None and prop_elem.text:
        try:
            return int(prop_elem.text)
        except ValueError:
            pass
    return default

def extract_http_body(elem) -> str:
    """Extract HTTP request body from HTTPSamplerProxy element"""
    # Check for raw body
    post_body_raw = get_bool_prop(elem, "HTTPSampler.postBodyRaw", False)
    if post_body_raw:
        arg_elem = elem.find('.//elementProp[@elementType="HTTPArgument"]/stringProp[@name="Argument.value"]')
        if arg_elem is not None and arg_elem.text:
            return unescape(arg_elem.text)
    
    return "" 