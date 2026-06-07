from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    fmp_api_key: str = ""
    anthropic_api_key: str = ""
    fmp_base_url: str = "https://financialmodelingprep.com/api/v3"
    default_years: int = 5


settings = Settings()
