# Протокол проверки лабораторной №5

2 ноября 2026 г. Python 3.12, отдельные PostgreSQL 17 и Redis 7.4, настоящий prefork Celery worker (concurrency=2), Beat и Flower.

- `python scripts/check.py`: 49 passed (54.22 s), реальные PostgreSQL `_test`, Redis DB 13/14/15. Проверены сохранённые безопасность/кеш и новая атомарность, идемпотентность, outbox, retry, DLQ, retention. [JUnit](test-results.xml).
- `python scripts/integration.py`: настоящие API и worker, eager выключен; три HTTP-запроса в каждом режиме, задержки 2/1/1 с. [Результаты](demo/results.json), [график и скриншоты](measurements.md).
- Email заказа №5: RETRYING на первых трёх попытках, DEAD на четвёртой, отдельное сообщение dlq; PDF/SMS этого заказа успешны. Второй запуск PDF оставляет один эффект.
- Beat действительно запускает cleanup раз в 60 с. Проверены broker endpoint outage → сохранённый pending job → восстановление; worker offline → запуск → выполнение; SIGKILL дочернему worker во время PDF → redelivery → один эффект.
- Flower защищён Basic Auth, его API опрошен, скриншоты сняты Chromium. Нет реальной внешней отправки email/SMS или eager-замены воркера.
- Миграция проверена на заполненной схеме lab-04: существующий заказ сохранён, задним числом задания не созданы; downgrade до lab-04 и повторный upgrade успешны.
- Совместимые версии Celery и Redis-клиента закреплены в requirements.txt; проверены миграции/повторный upgrade/alembic check, Python compilation, pip check и git diff --check.

`scripts/integration.py --quick` также прошёл локально с реальными процессами. Временные результаты находятся в игнорируемом docs/ci/, полный отчёт ими не перезаписан.

CI выполняет те же pytest и отдельную real-process интеграцию в quick-режиме, с сокращёнными задержками и интервалом Beat; без браузерных снимков и SIGKILL. Состояние удалённого workflow смотрите в [Actions](../../.github/workflows/lab-05.yml).
