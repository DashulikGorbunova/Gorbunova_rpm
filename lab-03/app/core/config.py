from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str
    redis_url: str
    jwt_secret: SecretStr
    debug: bool = False
    allowed_origins: list[str] = Field(default_factory=lambda: ['http://localhost:3000'])
    jwt_issuer: str = 'sirius-food'
    jwt_audience: str = 'sirius-food-api'
    access_minutes: int = Field(default=15, ge=1, le=60)
    refresh_days: int = Field(default=7, ge=1, le=30)

    @field_validator('jwt_secret')
    @classmethod
    def strong_secret(cls, value):
        secret = value.get_secret_value()
        if len(secret.encode()) < 32 or secret.startswith('replace-'):
            raise ValueError('JWT_SECRET must contain at least 32 random bytes; replace example')
        return value

    @field_validator('allowed_origins')
    @classmethod
    def explicit_origins(cls, value):
        if not value or any(v == '*' or not v.startswith(('http://','https://')) for v in value):
            raise ValueError('Explicit HTTP(S) origins required')
        return value
