from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_application_credentials: str = ""
    kakao_rest_api_key: str = ""
    kakao_client_secret: str = ""
    kakao_redirect_uri: str = "http://localhost:8000/auth/kakao/callback"
    secret_key: str = "dev-secret-key"
    debug: bool = True

    # 텔레그램 채널 발송 (@licencedistribute)
    telegram_bot_token: str = ""               # @BotFather 발급 토큰 (.env에 보관)
    telegram_channel: str = "@licencedistribute"
    telegram_daily_hour: int = 18              # 발송 시각(KST)
    telegram_daily_minute: int = 0
    telegram_timezone: str = "Asia/Seoul"

    class Config:
        env_file = ".env"


settings = Settings()
