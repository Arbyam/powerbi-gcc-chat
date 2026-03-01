# Power BI GCC Chat

> Chat with your Power BI data using Azure OpenAI — ready for Government Community Cloud (GCC).

**One-command deployment:** `azd up`

## What Is This?

A full-stack web application that lets users ask natural language questions about their Power BI data. Powered by Azure OpenAI (function calling) and the Power BI REST API, it translates questions like *"What were total sales last quarter?"* into DAX queries, executes them, and returns conversational answers.

Built for **Azure Government (GCC Moderate)** — all endpoints are configurable for Commercial, GCC, and GCC High environments.

### Architecture

```
┌──────────────────┐    ┌──────────────────────────────┐    ┌────────────────┐
│  React Frontend  │───▶│  FastAPI Backend              │───▶│  Power BI      │
│  (Chat UI)       │    │  ┌─────────────────────────┐  │    │  REST API      │
│                  │◀───│  │  Azure OpenAI            │  │    │  (GCC/Comm.)   │
│                  │    │  │  Orchestrator             │  │    └────────────────┘
│                  │    │  │  (Function Calling)       │  │
│                  │    │  └─────────────────────────┘  │
│                  │    │  ┌─────────────────────────┐  │
│                  │    │  │  Security Layer           │  │
│                  │    │  │  PII Detection + Audit    │  │
│                  │    │  └─────────────────────────┘  │
└──────────────────┘    └──────────────────────────────┘
```

### Key Features

- **Natural Language to DAX** — Azure OpenAI translates questions into DAX queries
- **GCC Ready** — Configurable endpoints for Commercial, GCC, and GCC High
- **PII Detection** — Automatic masking of SSN, credit cards, emails, phone numbers
- **Audit Logging** — Every query logged in JSON for compliance
- **One-Command Deploy** — `azd up` provisions all Azure resources via Bicep
- **Streaming Responses** — Real-time token streaming via SSE
- **Schema Discovery** — Automatically explores dataset tables, columns, and measures

## Quick Start

### Prerequisites

- [Azure CLI](https://learn.microsoft.com/cli/azure/install-azure-cli)
- [Azure Developer CLI (azd)](https://learn.microsoft.com/azure/developer/azure-developer-cli/install-azd)
- [Docker](https://docs.docker.com/get-docker/) (for local dev or container builds)
- [Python 3.11+](https://python.org) (for local backend dev)
- [Node.js 20+](https://nodejs.org) (for local frontend dev)
- A **Power BI** workspace with a dataset (Premium/PPU/Fabric capacity required for DAX execution)
- An **Azure AD / Entra ID App Registration** with Power BI API permissions

### Deploy to Azure

```bash
# Login
azd auth login
az login

# Deploy everything (creates all resources + deploys containers)
azd up
```

You'll be prompted for:
- `environmentName` — any name (e.g., `powerbi-chat-dev`)
- `location` — Azure region (e.g., `eastus` or `usgovvirginia` for GCC)
- `tenantId`, `clientId`, `clientSecret` — Power BI service principal credentials

### Local Development

```bash
# Backend
cd src/backend
cp .env.example .env   # Fill in your values
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend (separate terminal)
cd src/frontend
npm install
npm run dev    # Opens at http://localhost:5173
```

Or with Docker Compose:
```bash
docker-compose up --build
# Frontend: http://localhost:3000
# Backend:  http://localhost:8000/docs
```

## GCC Configuration

Set `CLOUD_ENVIRONMENT=gcc` in your `.env` or as an Azure Container App environment variable.

| Setting | Commercial | GCC Moderate |
|---------|-----------|--------------|
| `CLOUD_ENVIRONMENT` | `commercial` | `gcc` |
| Power BI API | `api.powerbi.com` | `api.powerbigov.us` |
| Auth Scope | `analysis.windows.net/...` | `analysis.usgovcloudapi.net/...` |
| Azure Region | `eastus`, etc. | `usgovvirginia`, `usgovarizona` |

For **GCC High**, set `CLOUD_ENVIRONMENT=gcchigh`. The authority URL changes to `login.microsoftonline.us`.

## Project Structure

```
├── azure.yaml                  # Azure Developer CLI config
├── docker-compose.yml          # Local dev with Docker
├── infra/                      # Bicep IaC (provisioned by azd)
│   ├── main.bicep             # Main template
│   └── modules/               # Resource modules
├── src/
│   ├── backend/               # Python FastAPI
│   │   ├── app/
│   │   │   ├── main.py        # API endpoints
│   │   │   ├── orchestrator.py # Azure OpenAI + tool routing
│   │   │   ├── config.py      # GCC endpoint config
│   │   │   └── tools/         # Power BI connectors + security
│   │   ├── Dockerfile
│   │   └── requirements.txt
│   └── frontend/              # React + TypeScript
│       ├── src/
│       │   ├── App.tsx        # Main chat app
│       │   └── components/    # UI components
│       ├── Dockerfile
│       └── package.json
└── docs/                      # Additional documentation
```

## Security

- **PII Detection**: Automatically scans query results for SSN, credit cards, emails, phone numbers, IP addresses, and names. Masks them using configurable strategies (partial, full, hash, redact).
- **Audit Logging**: Every query, chat interaction, and tool call is logged in JSON format to `logs/audit.log`.
- **Managed Identity**: In Azure, uses system-assigned managed identity for Key Vault access (no secrets in environment variables).
- **Key Vault**: Client secrets and API keys stored in Azure Key Vault.

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/health` | GET | Health check |
| `/api/chat` | POST | Chat with AI (supports streaming) |
| `/api/workspaces` | GET | List Power BI workspaces |
| `/api/datasets/{id}` | GET | List datasets in workspace |
| `/api/query` | POST | Direct DAX query execution |
| `/api/config` | GET | Non-sensitive app config |

## Credits

Based on [sulaiman013/powerbi-mcp](https://github.com/sulaiman013/powerbi-mcp) — adapted for Azure OpenAI, full-stack deployment, and Government Cloud support.

## License

MIT
