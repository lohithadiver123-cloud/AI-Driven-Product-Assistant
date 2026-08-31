from pydantic import BaseSettings


class Settings(BaseSettings):
    MONGO_URI: str = ""
    MONGO_DB: str = "product_assistant"
    JWT_SECRET_KEY: str = "CHANGE_ME"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    class Config:
        env_file = ".env"


settings = Settings()
