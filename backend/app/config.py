from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List


class Settings(BaseSettings):
    DATABASE_URL: str = "sqlite+aiosqlite:///./diabetes_mvp.db"
    SECRET_KEY: str = "mvp-dev-secret-key-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 480
    ACCUCHEK_SERVICE_UUID: str = "00001808-0000-1000-8000-00805f9b34fb"
    ACCUCHEK_GLUCOSE_CHAR_UUID: str = "00002A18-0000-1000-8000-00805f9b34fb"
    BLE_SCAN_INTERVAL: int = 30
    BLE_SCAN_DURATION: int = 10
    MODEL_PATH: str = "./model/cnn_lstm_diabetes"
    RISK_THRESHOLD_LOW: float = 0.4
    RISK_THRESHOLD_HIGH: float = 0.7
    CLINICAL_DATA_EXPIRY_DAYS: int = 30
    CORS_ORIGINS: List[str] = ["http://localhost:5173", "http://localhost:3000"]

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_prefix="DIABETES_MVP_",
        extra="ignore",
    )


settings = Settings()
