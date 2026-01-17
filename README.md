# ASO Services Repository

Application services built on the ASO (Agent Service Orchestration) platform.

## Structure

```
services-repo/
├── libs/                    # Shared libraries
│   ├── aso-client/          # ASO platform client SDK
│   └── common/              # Common utilities
├── services/                # Application services
│   └── transcribe/          # Audio transcription service
├── tools/                   # Development and deployment tools
└── catalog.yaml             # Service catalog manifest
```

## Services

| Service | Description | Status |
|---------|-------------|--------|
| transcribe | Audio transcription using Whisper | active |

## Getting Started

### Prerequisites

- Python 3.11+
- Access to ASO platform services (dispatcher, eventstore, etc.)

### Adding a New Service

1. Create service directory under `services/`
2. Follow the standard structure:
   ```
   services/<name>/
   ├── src/           # Source code
   ├── docs/          # Service documentation
   ├── tests/         # Test files
   ├── requirements.txt
   └── README.md
   ```
3. Register in `catalog.yaml`
4. Register with Catalog API

### Using Shared Libraries

```python
from libs.aso_client import ASOClient
from libs.common import setup_logging
```

## Integration with ASO Platform

Services in this repo integrate with the ASO platform via:

- **Dispatcher**: Job scheduling and execution
- **EventStore**: Event sourcing and audit trail
- **ReadModel**: Queryable projections
- **MergeForge**: Git workspace management
- **Catalog API**: Service discovery

See [ASO Integration Guides](https://github.com/jurgenrgithub/aso-repo/tree/main/docs/integration) for details.

## Development

```bash
# Clone the repo
git clone https://github.com/jurgenrgithub/services-repo.git
cd services-repo

# Set up a service
cd services/transcribe
python -m venv venv
source venv/bin/activate  # or venv\Scripts\activate on Windows
pip install -r requirements.txt
```

## CODEOWNERS

Service teams own their directories. See `.github/CODEOWNERS` for details.
