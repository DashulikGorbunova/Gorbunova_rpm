# Проверка практической №3

Дата: 2 ноября 2026 г. Python 3.12, отдельные PostgreSQL 17 и Redis 7.4 из compose.yaml.

- `python scripts/check.py`: **24 passed**, 29.40 s. Использованы PostgreSQL `sirius_test` и Redis DB 15; миграции применены дважды, `alembic check` не обнаружил расхождений.
- Отдельная `sirius_migration_test`: upgrade head → повторный upgrade → downgrade base → upgrade head → alembic check — успешно.
- Реальный Uvicorn на loopback: health 200, локальный Swagger 200, создание заказа без Bearer 401.
- `python -m compileall -q app scripts tests`, `pip check`, `git diff --check` — успешно.
- `.env` и `.venv/` исключены Git; тестовые пароли не добавляются в миграции или настройки приложения.

В тестах проверены роли, IDOR, хеши паролей, 429/TTL/сбой Redis, JWT, отзыв и конкурентная ротация refresh, блокировка, профиль, меню, доставки, CORS, отключение production-документации и независимость Service от HTTP/ORM.

Сохранён [JUnit XML](test-results.xml). Единственное предупреждение — deprecation использования httpx в Starlette TestClient; оно относится к тестовому клиенту и не влияет на результаты. GitHub Actions запускает те же проверки при отправке изменений; состояние удалённого запуска смотрите на вкладке Actions.
