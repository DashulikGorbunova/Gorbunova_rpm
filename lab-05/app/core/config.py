from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str
    redis_url: str
    jwt_secret: SecretStr
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None
    notification_mode: str = 'celery'
    simulated_pdf_seconds: float = Field(default=2, ge=0, le=5)
    simulated_email_seconds: float = Field(default=1, ge=0, le=5)
    simulated_sms_seconds: float = Field(default=1, ge=0, le=5)
    demo_fail_email_modulo: int = Field(default=0, ge=0)
    demo_transient_email_failures: int = Field(default=0, ge=0, le=3)
    retry_base_seconds: float = Field(default=1, gt=0, le=60)
    beat_cleanup_seconds: float = Field(default=60, ge=.1)
    beat_outbox_seconds: float = Field(default=10, ge=.1)
    flower_basic_auth: SecretStr | None = None

    @property
    def broker_url(self):
        return self.celery_broker_url or self.redis_url.rsplit('/',1)[0]+'/1'

    @property
    def result_backend(self):
        return self.celery_result_backend or self.redis_url.rsplit('/',1)[0]+'/2'

    @field_validator('notification_mode')
    @classmethod
    def mode(cls, value):
        if value not in {'celery','sync'}:
            raise ValueError('notification_mode must be celery or sync')
        return value

    cache_enabled: bool = True
    cache_warmup: bool = True
    menu_ttl: int = Field(default=300, ge=1, le=3600)
    category_ttl: int = Field(default=600, ge=1, le=3600)
    cache_lock_seconds: int = Field(default=10, ge=1, le=60)
    cache_wait_seconds: float = Field(default=3.0, gt=0, le=10)
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
