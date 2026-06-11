"""Export FastAPI OpenAPI schema to openapi.json without starting the server."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from main import application  # type: ignore

output = Path(__file__).parent.parent / "openapi.json"
output.write_text(json.dumps(application.openapi(), indent=2))
print(f"Exported OpenAPI schema to {output}")
