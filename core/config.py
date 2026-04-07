from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_path: str = "alphacota.db"
    secret_key: str = "09d25e094faa6ca2556c818166b7a9563b93f7099f6f0f4caa6cf63b88e8d3e7"
    groq_api_key: str = ""

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()
