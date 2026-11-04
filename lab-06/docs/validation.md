# Проверка практической №6

`python scripts/check.py`: **60 passed**, 106.85 s. `python scripts/integration.py`: **PASS** с отдельными HTTP/gRPC-процессами.

- Миграции и alembic check на реальном PostgreSQL. Отдельная заполненная схема lab-05: существующая доставка сохранена, переход ON_THE_WAY поддержан, downgrade нормализует её в ASSIGNED без потери id/order/courier; повторный upgrade успешен. Повторная генерация Protobuf проверяется в CI.
- Сохранённый набор lab-05 проверяет безопасность, кеш и outbox/Celery; новые проверки обращаются к настоящему TCP gRPC-серверу.
- Проверены unary, old REST alias, поиск по order_id, отсутствие deliveries SQL на engine монолита, прямые RPC с чужим/отсутствующим JWT, некорректные int64 ID, 503 при недоступности, 504 при реальном дедлайне, три статуса streaming, два чат-клиента, запрет подмены sender и отзыв доступа во время потока.
- Отдельный scripts/integration.py запускает монолит и delivery разными OS-процессами, проверяет остановку/восстановление сервиса, streaming и двусторонний чат. [Результат](live/results.json), [server log](live/delivery.log), [monolith log](live/monolith.log).
- [JUnit](test-results.xml) сохраняет фактические количества/время; [workflow](../../.github/workflows/lab-06.yml) выполняет те же проверки в GitHub Actions.

Сеть не заменена eager/fake-вызовом. Задержка искусственного медленного RPC используется только в отдельном тесте отображения deadline в 504; реальная демонстрация проверяет deadline на ожидающем изменения stream. Секреты и JWT не записываются в Git.
