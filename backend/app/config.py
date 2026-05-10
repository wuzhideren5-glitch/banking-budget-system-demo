from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    data_dir: Path = Path(__file__).resolve().parent.parent.parent / "data"
    budget_year: int = 2026
    software_version: str = "2026_v2.13"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173"
    # 开发态：允许同一网段内用 http://<本机局域网IP>:5173 打开前端时的跨域（见 backend/.env.example）
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


settings = Settings()
