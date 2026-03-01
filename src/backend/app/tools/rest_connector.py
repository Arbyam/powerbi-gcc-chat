"""
Power BI REST API Connector — Cloud-native, GCC-aware
Replaces both the original REST and XMLA connectors with pure REST API calls.
Uses executeQueries endpoint for DAX (no ADOMD.NET/.NET dependency).
"""
import logging
from typing import Any, Dict, List, Optional

import msal
import requests

from ..config import get_settings

logger = logging.getLogger(__name__)


class PowerBIRestConnector:
    """Power BI connector using REST API — works on Linux, supports GCC endpoints."""

    def __init__(
        self,
        tenant_id: Optional[str] = None,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
    ):
        settings = get_settings()
        self.tenant_id = tenant_id or settings.tenant_id
        self.client_id = client_id or settings.client_id
        self.client_secret = client_secret or settings.client_secret
        self.base_url = settings.powerbi_api_url
        self.authority = settings.powerbi_authority
        self.scope = [settings.powerbi_scope]
        self.max_rows = settings.max_dax_rows
        self.access_token: Optional[str] = None

    # ------------------------------------------------------------------
    # Authentication
    # ------------------------------------------------------------------

    def authenticate(self) -> bool:
        """Authenticate via Service Principal (MSAL confidential client)."""
        try:
            app = msal.ConfidentialClientApplication(
                self.client_id,
                authority=self.authority,
                client_credential=self.client_secret,
            )
            result = app.acquire_token_for_client(scopes=self.scope)
            if "access_token" in result:
                self.access_token = result["access_token"]
                logger.info("Authenticated to Power BI Service")
                return True
            logger.error("Auth failed: %s", result.get("error_description", "Unknown"))
            return False
        except Exception as e:
            logger.error("Auth error: %s", e)
            return False

    def _ensure_auth(self) -> bool:
        if not self.access_token:
            return self.authenticate()
        return True

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------
    # Workspaces
    # ------------------------------------------------------------------

    def list_workspaces(self) -> List[Dict[str, Any]]:
        """List all workspaces accessible by the service principal."""
        if not self._ensure_auth():
            return []
        try:
            resp = requests.get(
                f"{self.base_url}/groups", headers=self._headers(), timeout=30
            )
            resp.raise_for_status()
            return [
                {"id": ws["id"], "name": ws["name"], "type": ws.get("type", "Workspace"), "state": ws.get("state", "Active")}
                for ws in resp.json().get("value", [])
            ]
        except Exception as e:
            logger.error("Failed to list workspaces: %s", e)
            return []

    # ------------------------------------------------------------------
    # Datasets
    # ------------------------------------------------------------------

    def list_datasets(self, workspace_id: str) -> List[Dict[str, Any]]:
        """List datasets in a workspace."""
        if not self._ensure_auth():
            return []
        try:
            resp = requests.get(
                f"{self.base_url}/groups/{workspace_id}/datasets",
                headers=self._headers(), timeout=30,
            )
            resp.raise_for_status()
            return [
                {
                    "id": ds["id"],
                    "name": ds["name"],
                    "configuredBy": ds.get("configuredBy", "Unknown"),
                    "isRefreshable": ds.get("isRefreshable", False),
                }
                for ds in resp.json().get("value", [])
            ]
        except Exception as e:
            logger.error("Failed to list datasets: %s", e)
            return []

    # ------------------------------------------------------------------
    # DAX Query Execution (replaces XMLA connector)
    # ------------------------------------------------------------------

    def execute_dax(
        self, workspace_id: str, dataset_id: str, dax_query: str
    ) -> Dict[str, Any]:
        """
        Execute a DAX query via the REST executeQueries endpoint.
        Requires the dataset to be in a Premium/PPU/Fabric capacity.
        """
        if not self._ensure_auth():
            return {"error": "Authentication failed"}
        try:
            url = f"{self.base_url}/groups/{workspace_id}/datasets/{dataset_id}/executeQueries"
            payload = {
                "queries": [{"query": dax_query}],
                "serializerSettings": {"includeNulls": True},
            }
            resp = requests.post(
                url, headers=self._headers(), json=payload, timeout=120
            )
            resp.raise_for_status()
            data = resp.json()

            # Parse the response into a flat list of rows
            results = data.get("results", [])
            if not results:
                return {"columns": [], "rows": [], "row_count": 0}

            tables = results[0].get("tables", [])
            if not tables:
                return {"columns": [], "rows": [], "row_count": 0}

            rows = tables[0].get("rows", [])
            columns = list(rows[0].keys()) if rows else []

            # Enforce row limit
            if len(rows) > self.max_rows:
                rows = rows[: self.max_rows]
                logger.warning("Truncated results to %d rows", self.max_rows)

            return {
                "columns": columns,
                "rows": rows,
                "row_count": len(rows),
                "truncated": len(rows) >= self.max_rows,
            }
        except requests.exceptions.HTTPError as e:
            error_body = ""
            try:
                error_body = e.response.json().get("error", {}).get("message", str(e))
            except Exception:
                error_body = str(e)
            logger.error("DAX execution failed: %s", error_body)
            return {"error": error_body}
        except Exception as e:
            logger.error("DAX execution error: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------

    def list_reports(self, workspace_id: str) -> List[Dict[str, Any]]:
        """List reports in a workspace."""
        if not self._ensure_auth():
            return []
        try:
            resp = requests.get(
                f"{self.base_url}/groups/{workspace_id}/reports",
                headers=self._headers(), timeout=30,
            )
            resp.raise_for_status()
            return [
                {"id": r["id"], "name": r["name"], "datasetId": r.get("datasetId", "")}
                for r in resp.json().get("value", [])
            ]
        except Exception as e:
            logger.error("Failed to list reports: %s", e)
            return []

    # ------------------------------------------------------------------
    # Refresh
    # ------------------------------------------------------------------

    def refresh_dataset(self, workspace_id: str, dataset_id: str) -> Dict[str, Any]:
        """Trigger a dataset refresh."""
        if not self._ensure_auth():
            return {"error": "Authentication failed"}
        try:
            url = f"{self.base_url}/groups/{workspace_id}/datasets/{dataset_id}/refreshes"
            resp = requests.post(url, headers=self._headers(), json={}, timeout=30)
            if resp.status_code == 202:
                return {"status": "refresh_triggered"}
            resp.raise_for_status()
            return {"status": "refresh_triggered"}
        except Exception as e:
            logger.error("Refresh error: %s", e)
            return {"error": str(e)}

    # ------------------------------------------------------------------
    # Dataset metadata (tables, measures, columns)
    # ------------------------------------------------------------------

    def get_tables_and_columns(
        self, workspace_id: str, dataset_id: str
    ) -> Dict[str, Any]:
        """
        Discover tables and columns using DISCOVER_STORAGE_TABLE_COLUMNS via DAX.
        Falls back to INFO.STORAGETABLECOLUMNS DMV if executeQueries works.
        """
        dax = """
        EVALUATE
        UNION(
            SELECTCOLUMNS(
                INFO.STORAGETABLECOLUMNS(),
                "TableName", [DIMENSION_NAME],
                "ColumnName", [ATTRIBUTE_NAME],
                "DataType", [DATATYPE]
            )
        )
        """
        result = self.execute_dax(workspace_id, dataset_id, dax)
        if "error" in result:
            # Fallback: try to infer schema from a small query
            return self._fallback_schema_discovery(workspace_id, dataset_id)
        return result

    def _fallback_schema_discovery(
        self, workspace_id: str, dataset_id: str
    ) -> Dict[str, Any]:
        """Attempt schema discovery via a simpler approach."""
        # Try getting tables via the REST API metadata endpoint
        if not self._ensure_auth():
            return {"error": "Auth failed"}
        try:
            # Use the dataset tables endpoint (limited info but works without Premium)
            url = f"{self.base_url}/groups/{workspace_id}/datasets/{dataset_id}"
            resp = requests.get(url, headers=self._headers(), timeout=30)
            resp.raise_for_status()
            dataset_info = resp.json()
            return {
                "dataset_name": dataset_info.get("name", "Unknown"),
                "note": "Full schema discovery requires Premium/PPU capacity. Use execute_dax with EVALUATE INFO.STORAGETABLECOLUMNS().",
            }
        except Exception as e:
            return {"error": str(e)}

    def get_measures(self, workspace_id: str, dataset_id: str) -> Dict[str, Any]:
        """Discover measures in the dataset via DMV."""
        dax = """
        EVALUATE
        SELECTCOLUMNS(
            INFO.MEASURES(),
            "TableName", [TableID],
            "MeasureName", [Name],
            "Expression", [Expression],
            "DataType", [DataType]
        )
        """
        return self.execute_dax(workspace_id, dataset_id, dax)
