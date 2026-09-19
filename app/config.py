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
    # Master Admin & Role Override Configuration
    master_admin_phone: str = "919265368695"
    test_user_role: str = "SALES"  # Set to "SALES" to test Fleet Approval; "MASTER_ADMIN" to revert in one word

    # Favlogix Automation & Bridge Configuration
    favlogix_bridge_url: str = ""  # Remote bridge URL (e.g. ngrok) when Render connects to local Chrome
    favlogix_url: str = "https://erp.favlogix.com"
    favlogix_remote_debug_port: int = 9222
    favlogix_timeout_seconds: int = 30

    executive_observer_phones: list = [
        "263776477481",  # Arshford Mariga
        "263732786786",  # Arif
        "263713866223",  # Zayn
        "263778405964",  # Faizan Patel
        "263718352518",  # Sujit
    ]
    
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

        # On local Windows without IPv6 routing, direct supabase domain fails DNS; fallback to IPv4 pooler
        if "db.pzprdduzmcagpzkxzlhz.supabase.co" in v_str:
            import socket
            try:
                socket.getaddrinfo("db.pzprdduzmcagpzkxzlhz.supabase.co", 5432)
            except socket.gaierror:
                v_str = v_str.replace("db.pzprdduzmcagpzkxzlhz.supabase.co:5432", "aws-0-ap-south-1.pooler.supabase.com:6543")
                v_str = v_str.replace("postgres:SupportIt_2026_Pass!", "postgres.pzprdduzmcagpzkxzlhz:SupportIt_2026_Pass!")

        return v_str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
