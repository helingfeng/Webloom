import tempfile
from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    app_name: str = "小鱼"
    database_url: str = "mysql+aiomysql://root:helingfeng@127.0.0.1:3306/fishcode?charset=utf8mb4"
    storage_dir: Path = BASE_DIR / "storage"
    scripts_dir: Path = BASE_DIR / "storage" / "scripts"
    executions_dir: Path = Path(tempfile.gettempdir()) / "atp_executions"
    playwright_timeout: int = 60_000
    script_execution_timeout: int = 120
    sql_query_timeout: int = 30
    sql_max_rows: int = 1000
    headless: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
settings.scripts_dir.mkdir(parents=True, exist_ok=True)
settings.executions_dir.mkdir(parents=True, exist_ok=True)
