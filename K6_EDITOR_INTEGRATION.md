# K6 Script Editor Integration Guide

## Overview
The K6 Script Editor is a powerful web-based tool for editing, validating, and testing K6 performance scripts with real-time feedback and syntax highlighting.

## Features
- ✅ **Monaco Editor Integration** - Professional code editor with syntax highlighting
- ✅ **Real-time Validation** - Instant K6 script syntax and structure validation
- ✅ **Script Templates** - Pre-built templates for common testing scenarios
- ✅ **Mock Script Execution** - Simulated test runs with realistic output
- ✅ **Response Validation** - Detailed analysis of test responses
- ✅ **Dark Theme Integration** - Consistent with your JMeter Toolkit design

## Files Created

### Frontend
- `templates/k6_editor.html` - Main K6 editor interface
- Updated `templates/base.html` - Added navigation links

### Backend
- `app/routers/k6_editor.py` - FastAPI router with all K6 functionality

## Integration Steps

### 1. Register the Router in FastAPI

Add to your main FastAPI application (typically `app/main.py`):

```python
from app.routers import k6_editor

app.include_router(k6_editor.router)
```

### 2. Install Required Dependencies

Add to your `requirements.txt`:

```txt
fastapi
pydantic
aiofiles  # For file operations if needed
```

### 3. Template Path Configuration

Ensure your FastAPI app can serve the HTML template. In `app/main.py`:

```python
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

app.mount("/static", StaticFiles(directory="static"), name="static")
templates = Jinja2Templates(directory="templates")
```

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/k6-editor` | GET | Serve the K6 editor page |
| `/api/k6/templates` | GET | Get all available templates |
| `/api/k6/template/{name}` | GET | Get specific template |
| `/api/k6/validate` | POST | Validate K6 script |
| `/api/k6/run` | POST | Execute K6 script (mock) |
| `/api/k6/format` | POST | Format K6 script code |
| `/api/k6/examples` | GET | Get code examples |
| `/api/k6/help` | GET | Get help documentation |

## Real K6 Integration (Optional)

To enable actual K6 script execution, install K6 and modify the `/api/k6/run` endpoint:

```bash
# Install K6
curl https://github.com/grafana/k6/releases/download/v0.46.0/k6-v0.46.0-linux-amd64.tar.gz -L | tar xvz --strip-components 1
```

## Security Considerations

⚠️ **Important**: The current implementation includes mock script execution for demo purposes. For production:

1. **Sandbox script execution** in containers
2. **Limit execution time** and resources
3. **Validate script content** before execution
4. **Use proper authentication** and authorization
5. **Rate limit** API endpoints

## Customization

### Adding New Templates
Add templates to the `K6_TEMPLATES` dictionary in `k6_editor.py`:

```python
K6_TEMPLATES["custom"] = '''
import http from 'k6/http';
// Your custom template here
'''
```

### Modifying Validation Rules
Update the `validate_script()` function to add custom validation rules:

```python
# Add custom checks
if 'your_pattern' not in code:
    validation_result.warnings.append("Your custom warning")
```

## Frontend Customization

The editor uses Monaco Editor with the following features:
- JavaScript syntax highlighting
- K6 API IntelliSense
- Real-time error detection
- Code formatting
- Template loading

### Monaco Editor Configuration
Located in the `<script>` section of `k6_editor.html`:

```javascript
editor = monaco.editor.create(document.getElementById('editor'), {
  value: templates.basic,
  language: 'javascript',
  theme: 'vs-dark',
  // ... other options
});
```

## Navigation Integration

The K6 Editor has been integrated into your navigation:
- ✅ Header navigation (`/k6-editor`)
- ✅ Home page feature card
- ✅ Footer links

## Troubleshooting

### Common Issues

1. **Template not found**: Ensure `templates/k6_editor.html` exists
2. **Monaco Editor not loading**: Check CDN connectivity
3. **API endpoints not working**: Verify router registration

### Debug Mode
Enable debug logging in your FastAPI app:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

## Next Steps

1. **Test the integration** by visiting `/k6-editor`
2. **Customize templates** for your use cases  
3. **Add real K6 execution** if needed
4. **Implement user authentication** for production
5. **Add script saving/loading** functionality

## Support

The K6 Editor includes:
- 📖 Built-in help system (`/api/k6/help`)
- 💡 Code examples (`/api/k6/examples`)
- 🎯 Multiple script templates
- ✅ Real-time validation feedback

Enjoy your new K6 Script Editor! 🚀 