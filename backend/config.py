from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    google_application_credentials: str = ""
    kakao_rest_api_key: str = ""
    kakao_client_secret: str = ""
    kakao_redirect_uri: str = "http://localhost:8000/auth/kakao/callback"
    secret_key: str = "dev-secret-key"
    debug: bool = True

    class Config:
        env_file = ".env"


settings = Settings()
