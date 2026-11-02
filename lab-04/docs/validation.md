# Проверка лабораторной №4

2 ноября 2026 г. Python 3.12, PostgreSQL 17 и Redis 7.4 в выделенном Compose-проекте rpm-lab04.

- `python scripts/check.py`: **40 passed**, 65.29 s, PostgreSQL sirius_test и Redis DB 15. Alembic применён дважды, `alembic check` не обнаружил расхождений. [JUnit](test-results.xml).
- Сохранены 24 теста безопасности третьей работы; добавлены 16 проверок кеша и времени жизни соединений, в том числе конкурентные single-flight и invalidate-vs-loader, недоступность Redis, TTL, повреждённый JSON, warm-up и режим baseline.
- Отдельная миграционная база: версия lab-03 → вставка существующего блюда → upgrade → проверка сохранности и категории «Общее» → повторный upgrade → downgrade до lab-03 → upgrade → alembic check. Успешно.
- Два реальных Locust-прогона достигают 500 пользователей (spawn 10/с), результат проверяется скриптом. PostgreSQL SELECT измерены pg_stat_statements, без искусственных задержек или отключения JWT. Итог: [таблицы и график](measurements.md).
- Первая диагностическая попытка выявила исчерпание пула. После одинаковой для обоих режимов починки времени жизни read-соединений прогоны повторены. Ошибочная попытка сохранена [отдельно](load/initial-pool-exhaustion/README.md) и не смешана с основным сравнением.
- `python -m compileall`, `pip check`, `git diff --check` — успешно. `.env`, виртуальное окружение и действующий Bearer не входят в Git.

Единственное предупреждение pytest — deprecation тестового клиента httpx в Starlette; тесты выполняются успешно. [CI workflow](../../.github/workflows/lab-04.yml) использует PostgreSQL/Redis services и тот же scripts/check.py.
