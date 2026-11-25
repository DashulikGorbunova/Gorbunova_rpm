# Практическая №9 — Observability
**Горбунова Дарья** · Сириус.Еда. Продолжение lab07, отдельная копия.

## Архитектура
HTTP → создание заказа → оплата → PostgreSQL outbox → RabbitMQ → кухня.
Один X-Correlation-ID передаётся при создании и оплате; outbox сохраняет ID и traceparent в JSON. Relay переносит контекст в AMQP headers, consumer извлекает его. Трейс оплаты включает публикацию и обработку кухни; создание заказа — отдельный HTTP trace с тем же correlation ID. JWT и идемпотентность сохранены.

## Запуск (macOS)
Из lab09:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/init_env.py
docker compose up -d --wait
alembic upgrade head
mkdir -p logs
```
В .env установить DEBUG=true, NOTIFICATION_MODE=sync для демонстрации без Celery. SENTRY_DSN заполнить своим DSN (не коммитить). OTLP endpoint создаётся скриптом. В отдельных терминалах с активной venv из lab09:
```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 | tee logs/app.log
python -m app.workers.kitchen_consumer | tee logs/kitchen.log
python -m app.workers.outbox_worker | tee logs/outbox.log
python delivery_worker.py
python -m app.workers.compensation_consumer
python delivery_server.py
```
API слушает все интерфейсы для доступа Prometheus из Docker; запускать только в доверенной локальной сети. Остановить предыдущие лабораторные на порту 8000. Grafana на 3001, чтобы не конфликтовать с Next.js.

## Расследование demo-42
Через Swagger http://localhost:8000/docs создать студента и блюдо (администратор создаётся командой python -m app.bootstrap admin@example.org). Получить JWT студента, подставить TOKEN и ITEM_ID:
```bash
curl -i -X POST http://localhost:8000/orders/create -H "Authorization: Bearer $TOKEN" -H 'X-Correlation-ID: demo-42' -H 'Content-Type: application/json' -d "{\"item_id\":$ITEM_ID,\"quantity\":1}"
# Подставить полученный order_id в ORDER_ID
curl -i -X POST "http://localhost:8000/orders/$ORDER_ID/pay" -H "Authorization: Bearer $TOKEN" -H 'X-Correlation-ID: demo-42'
jq -R 'fromjson? | select(.correlation_id=="demo-42")' logs/app.log logs/outbox.log logs/kitchen.log
curl -s http://localhost:8000/metrics | grep http_requests_total
```
Ожидаемые события: order_created, order_paid, event_published, order_received. Сравнить order_id и время. Повторная оплата не создаёт новое событие. Для нагрузки выполнить несколько GET /health и авторизованных GET /menu/items.
Prometheus http://localhost:9090/targets: три UP. Grafana http://localhost:3001 (admin/admin, локальный учебный пароль): автоматически созданный dashboard, RPS, p95, 5xx, очередь кухни, Redis hit rate. Выбрать интервал расследования. Метрики агрегированы, correlation ID не является label.
Sentry: curl -i -H 'X-Correlation-ID: demo-42' http://localhost:8000/debug/observability-error (только DEBUG=true). Проверить событие с тегом correlation_id.
Jaeger http://localhost:16686: выбрать monolith и операцию оплаты, найти spans OrderService.pay, RabbitMQ.publish, kitchen.consume; сравнить длительности. При остановке API кеш не влияет на трассировку.

## Контрольные вопросы
1. Мониторинг отвечает на заранее заданные вопросы, observability помогает исследовать новые проблемы.
2. Correlation ID связывает бизнес-операцию между сервисами; без него трудно сопоставить логи.
3. stdout собирается контейнером или внешним агентом, файлы внутри контейнера могут исчезнуть.
4. Correlation ID связывает бизнес-операцию, trace ID — технический путь выполнения.
5. RED: Rate, Errors, Duration.
6. Span — отдельная операция с временем и атрибутами; trace — дерево связанных spans.
7. Context propagation — перенос traceparent между процессами.
8. Sentry группирует исключения и показывает stack trace и контекст; логи фиксируют также обычные события.
9. Кардинальность — число уникальных комбинаций labels; ID заказов в labels создают слишком много рядов.
10. request.state хранит данные запроса, call_next передаёт управление следующему обработчику.

## Статус
Код и конфигурация подготовлены. Реальный запуск Docker, проверка графиков, расследование и Sentry/Jaeger не выполнены в среде разработки. Sentry требует личного DSN. Логи приложения пишутся JSON в stdout; сторонние библиотеки могут выводить обычные диагностические строки. Скриншоты и результаты не выдуманы.
