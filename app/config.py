import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

class Settings(BaseSettings):
    phone_number_id: str = "1277210488805791"
    meta_access_token: str = "EAAaI4UFujrkBSMFJwtX8hvXppfQDf1U5btRTA9aadNWUkaoCky1D51veToyZCRIAggIQ2qSsyMKI0kjLT2tUAoRXyjZCB0qTRdNBfa3dkvA2IBJiJ9ZAkaMuiLQ94WqdwwOfkSKtU1cvcdhdAlaAAISEq47UFuwacbY4Ue709F9MVfqpY05sKHD7ZAZBhhQZDZD"
    meta_graph_version: str = "v19.0"
    meta_display_number: str = "+91 93282 95424"
    verify_token: str = "itsupport_meta_secret_123"
    
    database_url: str = "sqlite+aiosqlite:///./itsupport.db"

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        if not v:
            return "sqlite+aiosqlite:///./itsupport.db"
        
        # Render PostgreSQL default format fix: postgres:// or postgresql:// -> postgresql+asyncpg://
        if v.startswith("postgres://"):
            v = v.replace("postgres://", "postgresql+asyncpg://", 1)
        elif v.startswith("postgresql://") and not v.startswith("postgresql+asyncpg://"):
            v = v.replace("postgresql://", "postgresql+asyncpg://", 1)
            
        return v

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
