"""
Configuration module for Power BI GCC Chat
Handles environment-aware endpoint configuration for Commercial, GCC, and GCC High clouds.
"""
import os
from enum import Enum
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import Field


class CloudEnvironment(str, Enum):
    """Azure cloud environment"""
    COMMERCIAL = "commercial"
    GCC = "gcc"
    GCC_HIGH = "gcchigh"


# Endpoint mappings per cloud environment
CLOUD_ENDPOINTS = {
    CloudEnvironment.COMMERCIAL: {
        "powerbi_api": "https://api.powerbi.com/v1.0/myorg",
        "powerbi_authority": "https://login.microsoftonline.com",
        "powerbi_scope": "https://analysis.windows.net/powerbi/api/.default",
        "powerbi_resource": "https://analysis.windows.net/powerbi/api",
        "openai_suffix": "openai.azure.com",
        "arm_endpoint": "https://management.azure.com",
        "keyvault_suffix": "vault.azure.net",
    },
    CloudEnvironment.GCC: {
        "powerbi_api": "https://api.powerbigov.us/v1.0/myorg",
        "powerbi_authority": "https://login.microsoftonline.com",
        "powerbi_scope": "https://analysis.usgovcloudapi.net/powerbi/api/.default",
        "powerbi_resource": "https://analysis.usgovcloudapi.net/powerbi/api",
        "openai_suffix": "openai.azure.us",
        "arm_endpoint": "https://management.usgovcloudapi.net",
        "keyvault_suffix": "vault.usgovcloudapi.net",
    },
    CloudEnvironment.GCC_HIGH: {
        "powerbi_api": "https://api.high.powerbigov.us/v1.0/myorg",
        "powerbi_authority": "https://login.microsoftonline.us",
        "powerbi_scope": "https://analysis.usgovcloudapi.net/powerbi/api/.default",
        "powerbi_resource": "https://analysis.usgovcloudapi.net/powerbi/api",
        "openai_suffix": "openai.azure.us",
        "arm_endpoint": "https://management.usgovcloudapi.net",
        "keyvault_suffix": "vault.usgovcloudapi.net",
    },
}


class Settings(BaseSettings):
    """Application settings — loaded from environment variables"""

    # === Cloud Environment ===
    cloud_environment: CloudEnvironment = Field(
        default=CloudEnvironment.COMMERCIAL,
        description="Target cloud: commercial, gcc, or gcchigh"
    )

    # === Power BI Service Principal ===
    tenant_id: str = Field(default="", description="Azure AD / Entra ID tenant ID")
    client_id: str = Field(default="", description="App registration client ID")
    client_secret: str = Field(default="", description="App registration client secret (local dev only — use Managed Identity in Azure)")

    # === Azure OpenAI ===
    azure_openai_endpoint: str = Field(default="", description="Azure OpenAI resource endpoint URL")
    azure_openai_key: str = Field(default="", description="Azure OpenAI API key (local dev only — use Managed Identity in Azure)")
    azure_openai_deployment: str = Field(default="gpt-4o", description="Deployment name for the chat model")
    azure_openai_api_version: str = Field(default="2024-12-01-preview", description="Azure OpenAI API version")

    # === Security ===
    enable_pii_detection: bool = Field(default=True, description="Enable PII detection and masking")
    enable_audit: bool = Field(default=True, description="Enable audit logging")
    enable_policies: bool = Field(default=True, description="Enable access policy enforcement")

    # === App ===
    log_level: str = Field(default="INFO", description="Logging level")
    cors_origins: str = Field(default="http://localhost:5173,http://localhost:3000", description="Comma-separated CORS origins")
    max_dax_rows: int = Field(default=1000, description="Maximum rows returned from DAX queries")

    # === Optional: Azure Key Vault ===
    keyvault_name: Optional[str] = Field(default=None, description="Azure Key Vault name for secrets")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8", "case_sensitive": False}

    @property
    def endpoints(self) -> dict:
        """Get cloud-specific endpoints"""
        return CLOUD_ENDPOINTS[self.cloud_environment]

    @property
    def powerbi_api_url(self) -> str:
        return self.endpoints["powerbi_api"]

    @property
    def powerbi_authority(self) -> str:
        return f"{self.endpoints['powerbi_authority']}/{self.tenant_id}"

    @property
    def powerbi_scope(self) -> str:
        return self.endpoints["powerbi_scope"]

    @property
    def cors_origins_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",")]


# Singleton
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
