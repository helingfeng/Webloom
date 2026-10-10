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

    # ---- 执行队列（Redis + arq worker）----
    redis_url: str = "redis://127.0.0.1:6379/0"
    # worker 最大并发执行数（每个执行 = 1 个 Python 子进程 + 1 个 Chromium 实例）
    max_concurrent_executions: int = 5

    # ---- 数据采集缓存与连接池 ----
    # 数据视图预取结果 TTL 缓存秒数（仅 worker 侧；0 关闭缓存）
    cache_ttl_seconds: int = 30
    # 数据源外部库连接池
    datasource_pool_size: int = 5
    datasource_max_overflow: int = 10
    # 平台主库连接池
    database_pool_size: int = 20
    database_max_overflow: int = 40

    # ---- 开放平台 ----
    # 开放接口签名时间窗（秒），X-Timestamp 与服务器时间偏差超过该值拒绝
    open_api_sign_ttl_seconds: int = 300
    # 代理接口转发目标（平台自身 API 地址）
    open_api_internal_base_url: str = "http://127.0.0.1:8000"

    class Config:
        env_file = ".env"


settings = Settings()
settings.scripts_dir.mkdir(parents=True, exist_ok=True)
settings.executions_dir.mkdir(parents=True, exist_ok=True)
