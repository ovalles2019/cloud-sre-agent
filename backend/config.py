"""Application configuration."""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

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


@lru_cache
def get_settings() -> Settings:
    return Settings()
