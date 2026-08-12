import os
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    phone_number_id: str = "1145527058653682"
    meta_access_token: str = "EAAaI4UFujrkBSO2MlhGj0DO7J5k4Dr0QMZAMMqLd4tZCA4xSl72a8WH6AA8p0mqFsIbCvsYQOdSpmKPHDTZBwqX2TyaVdeHjVvhHeIyHLuFxC4mZASf4q8Uvmfnlx2MLgrAEuZB0c8Tsj0Ei5vnhXhlSA2K0YRHKcnMLDUz7hJ3RCJEcz2ZBIbUhiLn7yzX4lmQZAPScrNgoe9jZCSWgG04ofKjPGkeKSOLNlv4HKCBIxS013vys8QdtqqT3Q8yXXnPYSSNSXEd4RWPPvWUAss1XqIuhLlUGAYhKogZDZD"
    meta_graph_version: str = "v19.0"
    meta_display_number: str = "+1 555-672-9057"
    verify_token: str = "itsupport_meta_secret_123"
    
    database_url: str = "sqlite+aiosqlite:///./itsupport.db"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

settings = Settings()
