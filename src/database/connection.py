import pyodbc
from pydantic_settings import BaseSettings
from functools import lru_cache

class Settings(BaseSettings):
    DB_SERVER: str
    DB_DATABASE: str
    DB_USER: str
    DB_PASSWORD: str
    HEADLESS: bool = True
    
    TWITTER_USER: str = ""
    TWITTER_PASS: str = ""
    INSTAGRAM_USER: str = ""
    INSTAGRAM_PASS: str = ""
    FACEBOOK_USER: str = ""
    FACEBOOK_PASS: str = ""
    
    class Config:
        env_file = ".env"

@lru_cache()
def get_settings():
    return Settings()

class DatabaseConnection:
    def __init__(self):
        self.settings = get_settings()
        self.connection_string = (
            f'DRIVER={{SQL Server}};'
            f'SERVER={self.settings.DB_SERVER};'
            f'DATABASE={self.settings.DB_DATABASE};'
            f'UID={self.settings.DB_USER};'
            f'PWD={self.settings.DB_PASSWORD}'
        )

    def get_connection(self):
        return pyodbc.connect(self.connection_string, timeout=10)
