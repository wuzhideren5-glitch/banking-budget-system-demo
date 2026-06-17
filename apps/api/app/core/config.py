from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

API_ROOT = Path(__file__).resolve().parents[2]
REPO_ROOT = Path(__file__).resolve().parents[4]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=API_ROOT / ".env", extra="ignore")

    repo_root: Path = REPO_ROOT
    resources_dir: Path = REPO_ROOT / "resources"
    data_dir: Path = REPO_ROOT / "var" / "data"
    download_template_dir: Path = REPO_ROOT / "resources" / "download_template"
    knowledge_base_dir: Path = REPO_ROOT / "resources" / "knowledge_base"
    business_inputs_dir: Path = REPO_ROOT / "resources" / "business_inputs"
    agent_log_dir: Path = REPO_ROOT / "var" / "logs" / "agent"
    budget_year: int = 2026
    software_version: str = "2026_v2.13"
    cors_origins: str = "http://127.0.0.1:8443,http://localhost:8443,http://guanheng.webank.com:8443,http://guanheng.webank.com"
    # 测试环境：允许同一网段内用 http://<服务器IP>:8443 或域名打开前端时的跨域（见 apps/api/.env）
    cors_origin_regex: str = ""
    local_user_id: str = "local"
    local_user_name: str = "Arthur"
    local_user_role: str = "预算主管"
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    # 飞书机器人（长连接事件）；未启用时不连接开放平台
    feishu_enabled: bool = False
    feishu_app_id: str = ""
    feishu_app_secret: str = ""
    feishu_domain: str = "https://open.feishu.cn"
    # 仅内网/排障：跳过 WSS 证书校验（生产环境勿开启）
    feishu_insecure_ssl: bool = False

    # MySQL 数据库连接配置
    MYSQL_HOST: str = "localhost"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = ""
    MYSQL_DATABASE: str = "banking_budget"
    MYSQL_POOL_MINSIZE: int = 2
    MYSQL_POOL_MAXSIZE: int = 10
    MYSQL_POOL_RECYCLE: int = 3600


settings = Settings()
