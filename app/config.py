import os
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator

class Settings(BaseSettings):
    phone_number_id: str = "1277210488805791"
    meta_access_token: str = "EAAaI4UFujrkBSMFJwtX8hvXppfQDf1U5btRTA9aadNWUkaoCky1D51veToyZCRIAggIQ2qSsyMKI0kjLT2tUAoRXyjZCB0qTRdNBfa3dkvA2IBJiJ9ZAkaMuiLQ94WqdwwOfkSKtU1cvcdhdAlaAAISEq47UFuwacbY4Ue709F9MVfqpY05sKHD7ZAZBhhQZDZD"
    meta_graph_version: str = "v19.0"
    meta_display_number: str = "+91 93282 95424"
    verify_token: str = "itsupport_meta_secret_123"
    master_group_phone: str = "HQ0msg8LFOp1i3bZoB2V3H"
    master_group_link: str = "https://chat.whatsapp.com/HQ0msg8LFOp1i3bZoB2V3H"
    
    database_url: str = "sqlite+aiosqlite:///./itsupport.db"

    @field_validator("database_url", mode="before")
    @classmethod
    def assemble_db_connection(cls, v: str) -> str:
        if not v:
            return "sqlite+aiosqlite:///./itsupport.db"
        
        v_str = str(v).strip()
        
        # Ensure asyncpg driver prefix for any PostgreSQL scheme
        if v_str.startswith("postgres://"):
            v_str = "postgresql+asyncpg://" + v_str[11:]
        elif v_str.startswith("postgresql://"):
            v_str = "postgresql+asyncpg://" + v_str[13:]
        elif v_str.startswith("postgres+asyncpg://"):
            v_str = "postgresql+asyncpg://" + v_str[19:]

        return v_str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
