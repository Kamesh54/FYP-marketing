# External User Agent (A2A Demo)

This is a separate user-agent service that demonstrates external A2A interoperability with the orchestrator.

## Flow

1. Observer listens for `Product_Added` event (`POST /events/product-added`)
2. Content creator generates summary
3. Negotiation sends proposal to orchestrator (`campaigns.propose`)
4. Acceptance triggers execution (`campaigns.accept`)
5. Feedback loop watches completion and exposes UI-ready state + metrics hooks

## Run

```bash
pip install -r requirements.txt
uvicorn external_user_agent.main:app --host 127.0.0.1 --port 8091 --reload
```

## Environment

Create `.env` in this folder:

```env
ORCHESTRATOR_BASE_URL=http://127.0.0.1:8004
ORCHESTRATOR_EMAIL=demo@example.com
ORCHESTRATOR_PASSWORD=your-password
ORCHESTRATOR_BRAND=
```

If `ORCHESTRATOR_BRAND` is empty, orchestrator auto-selects the user's first brand.

## Endpoints

- `GET /` health and capabilities
- `POST /events/product-added` create workflow from product event
- `POST /workflows/{workflow_id}/propose` send proposal to orchestrator
- `POST /workflows/{workflow_id}/accept` accept proposal and execute
- `GET /workflows/{workflow_id}` read current lifecycle state
- `GET /workflows` list all local workflows
