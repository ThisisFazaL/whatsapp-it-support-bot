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
    fleet_admin_phone: str = "263718352518"  # Sujit (+263 71 835 2518) receives all sales fleet activity alerts
    test_user_role: str = "SALES"  # Set to "SALES" to test Fleet Approval; "MASTER_ADMIN" to revert in one word

    # Fleet Subsystem Roles & Operational Phones
    zayn_phone: str = "263713866223"
    edward_phone: str = "263715025982"
    sales_admin_tg_phone: str = "263718352518"  # Tagoneswa Hardware Sales Admin (Sujit fallback)
    sales_admin_lg_phone: str = "263718352518"  # LG Plast Sales Admin
    sales_admin_kreckle_phone: str = "263718352518"  # Kreckle Sales Admin
    accounts_phones: list = ["263718352518", "919265368695"]
    logistics_manager_phone: str = "263718352518"

    # Favlogix Direct Background API Configuration (Option 1 - Headless)
    favlogix_api_enabled: bool = True
    favlogix_api_url: str = "https://api.favlogix.com/api"
    favlogix_organization: str = "sandbox"  # Organization name (e.g. 'sandbox') or organization ID ('019bdf9df302700')
    favlogix_email: str = "faizanpatel@favlogix.com"
    favlogix_password: str = ""
    favlogix_auth_token: str = ""

    # Favlogix Automation & Bridge Configuration (Fallback)
    favlogix_bridge_url: str = "https://uninjured-seducing-cycle.ngrok-free.dev"  # Remote bridge URL (e.g. ngrok) when Render connects to local Chrome
    favlogix_url: str = "https://erp.favlogix.com"
    favlogix_packaging_lists_path: str = "/inventory/packaging-lists"
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

        # Ensure IPv4 transaction pooler for Supabase (resolves both IPv6 Windows DNS issues and connection limits)
        if "db.pzprdduzmcagpzkxzlhz.supabase.co" in v_str:
            v_str = v_str.replace("db.pzprdduzmcagpzkxzlhz.supabase.co:5432", "aws-0-ap-south-1.pooler.supabase.com:6543")
            v_str = v_str.replace("postgres:SupportIt_2026_Pass!", "postgres.pzprdduzmcagpzkxzlhz:SupportIt_2026_Pass!")

        return v_str

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
