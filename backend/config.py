"""Application configuration."""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Cloud SRE Agent"
    environment: Literal["local", "dev", "prod"] = "local"
    aws_region: str = "us-east-1"

    # Bedrock
    bedrock_model_id: str = "anthropic.claude-3-5-sonnet-20241022-v2:0"
    bedrock_agent_id: str = ""
    bedrock_agent_alias_id: str = ""

    # Storage
    dynamodb_incidents_table: str = "cloud-sre-incidents"
    dynamodb_approvals_table: str = "cloud-sre-approvals"
    use_local_store: bool = True

    # Demo / simulation when AWS creds unavailable
    demo_mode: bool = True
    demo_seed: int = 42

    # Approval gate
    require_approval_for_writes: bool = True
    approval_ttl_hours: int = 24

    # Observability targets (comma-separated in env)
    monitored_services: str = "ec2,rds,lambda,ecs"
    cost_anomaly_threshold_pct: float = 15.0

    # Public URL (for links in incident reports)
    public_base_url: str = ""

    @model_validator(mode="after")
    def resolve_runtime_mode(self) -> Settings:
        has_aws_creds = bool(os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))
        demo_env = os.environ.get("DEMO_MODE", "").lower()

        if demo_env == "false" or (has_aws_creds and demo_env not in {"true", "1", "yes"}):
            self.demo_mode = False
            if os.environ.get("USE_LOCAL_STORE", "").lower() == "false":
                self.use_local_store = False

        if not self.public_base_url:
            render_url = os.environ.get("RENDER_EXTERNAL_URL", "")
            if render_url:
                self.public_base_url = render_url.rstrip("/")

        if self.public_base_url and self.public_base_url.endswith("/"):
            self.public_base_url = self.public_base_url.rstrip("/")

        return self

    @property
    def runtime_label(self) -> str:
        if self.demo_mode:
            return "demo"
        return "live-aws"


@lru_cache
def get_settings() -> Settings:
    return Settings()
