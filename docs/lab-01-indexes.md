# Лабораторная работа №1. Индексы и EXPLAIN ANALYZE в PostgreSQL

## Условия и воспроизводимость

Работа выполнена на реальном PostgreSQL 17 в выделенном Docker-контейнере. Версия, параметры и число строк сохранены в [environment.txt](plans/environment.txt). Запуск описан в [README](../README.md). Полные планы с `ANALYZE, BUFFERS` доступны по ссылкам таблиц; [все тестовые запросы и планы](plans/results.json), [сервисные запросы и планы](plans/service-results.json). Файл `scripts/experiments.py` фиксирует точный порядок DDL и запросов.

Параметры планировщика не принуждались: `enable_seqscan` и другие способы искусственного выбора плана не использовались. Время включает прогрев кеша, нагрузку машины и измерительные накладные расходы EXPLAIN ANALYZE. Каждый запрос измерен один раз на этапе; малые различия в долях миллисекунды не доказывают улучшение. Для эксплуатационного решения нужны серии запусков и медиана/p95. PostgreSQL cost — условная оценка, не миллисекунды. Actual Rows у узла — среднее за один loop; для параллельных сканирований учитывается Actual Loops. BUFFERS показывает обращения к буферам, а не число уникальных строк.

## 1–2. Таблица и данные

[SQL подготовки](../sql/01-seed.sql) создаёт orders с полями из задания и 1 000 000 строк, четыре примерно равновероятных статуса, случайные пользователей и даты за два года; выполняется ANALYZE. `setseed(0.42)` фиксирует последовательность random в сессии, даты зависят от момента запуска.

Для задания 17 распределение отдельно изменено до 1% NEW. Для задания 21 добавлена когорта активного пользователя 123 (1000 заказов PAID в последние 30 дней), чтобы LIMIT 50 проверялся на непустой выборке. Эти изменения выполняются после начальных экспериментов и отражены в скрипте. Сервис использует копию этой последней выборки; это синтетические данные, не пользовательские заказы.

## 3–4. EXPLAIN и EXPLAIN ANALYZE

[Обычный EXPLAIN](plans/03-explain.txt) показывает предполагаемый план без выполнения SELECT. EXPLAIN ANALYZE действительно выполняет запрос и добавляет фактическое время, строки и loops, поэтому может работать существенно дольше. Estimated rows основаны на статистике ANALYZE; actual rows — на реально обработанных данных. Расхождение возникает из-за выборочной статистики, корреляции условий и изменений данных.

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [04-user-before](plans/04-user-before.json) | Gather, Seq Scan | 0.288 | 28.32 | 9 | — |

Изначально дополнительного индекса по user_id нет: строки ищутся чтением таблицы и проверкой фильтра. В JSON сохранены `Rows Removed by Filter`, `Actual Rows`, `Actual Loops`, Planning Time и Execution Time.

## 5. Sequential Scan

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [05-all](plans/05-all.json) | Seq Scan | 0.148 | 105.778 | 1000000 | — |
| [05-amount](plans/05-amount.json) | Seq Scan | 0.256 | 160.743 | 1000000 | — |

Оба запроса возвращают всю или почти всю таблицу. Последовательное чтение дешевле обхода индекса с последующими обращениями почти ко всем страницам heap. Seq Scan полезен для больших долей таблицы, маленьких таблиц и массовой аналитики, поэтому сам по себе не является ошибкой.

## 6. Первый B-tree

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [04-user-before](plans/04-user-before.json) | Gather, Seq Scan | 0.288 | 28.32 | 9 | — |
| [06-user-after](plans/06-user-after.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.343 | 0.159 | 9 | idx_orders_user_id |

В этом запуске: 28.32 → 0.159 мс; отношение времени до/после = 178.11. Это единичный замер, не статистическая оценка ускорения.

B-tree по user_id сужает поиск до нескольких кандидатов вместо миллиона. Число обработанных строк не равно числу возвращённых: до индекса сканируются все строки; после — индексные кандидаты и соответствующие heap-строки. Точные rows/loops и отбрасывания находятся в планах.

## 7–8. Статусы и селективность

Распределение `status | count | percent`:

```text
CANCELLED|249825|24.98
DELIVERED|250067|25.01
NEW|250109|25.01
PAID|249999|25.00
```

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [07-status-NEW](plans/07-status-NEW.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.31 | 52.735 | 250109 | idx_orders_status |
| [07-status-PAID](plans/07-status-PAID.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.274 | 53.217 | 249999 | idx_orders_status |
| [07-status-DELIVERED](plans/07-status-DELIVERED.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.29 | 51.108 | 250067 | idx_orders_status |
| [07-status-CANCELLED](plans/07-status-CANCELLED.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.292 | 54.323 | 249825 | idx_orders_status |

Около четверти таблицы приходится на каждый статус. Фактический выбор показан в таблице: наличие индекса не обязывает PostgreSQL выбирать обычный Index Scan или вообще использовать индекс. Большая доля результата увеличивает чтение heap; bitmap может сгруппировать обращения к страницам. При ещё большей доле Seq Scan может стать дешевле. Высокая селективность в смысле малого числа совпадений обычно делает индекс полезнее; термин нужно отличать от большой доли совпавших строк.

## 9. Диапазоны дат

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [09-range-before](plans/09-range-before.json) | Gather, Seq Scan | 0.297 | 88.626 | 9593 | — |
| [09-range-after](plans/09-range-after.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.424 | 11.051 | 9593 | idx_orders_created_at |
| [09-range-1-day](plans/09-range-1-day.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.395 | 3.167 | 1343 | idx_orders_created_at |
| [09-range-1-month](plans/09-range-1-month.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.328 | 22.142 | 41825 | idx_orders_created_at |
| [09-range-1-year](plans/09-range-1-year.json) | Seq Scan | 0.339 | 201.708 | 500136 | — |

B-tree поддерживает упорядоченный диапазон created_at. Узкий диапазон читает малую часть строк, год — примерно половину. Чем больше диапазон, тем меньше выгода индекса; выбор зависит также от корреляции физического размещения, кеша и стоимости случайного чтения.

## 10. Bitmap Scan

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [10-bitmap](plans/10-bitmap.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.397 | 22.685 | 41825 | idx_orders_created_at |

Bitmap Index Scan собирает bitmap адресов подходящих строк. Bitmap Heap Scan читает соответствующие страницы таблицы в удобном порядке и при необходимости перепроверяет условие (Recheck Cond). Для средней выборки это уменьшает случайные чтения по сравнению с Index Scan. При недостатке памяти bitmap может стать lossy и потребовать дополнительных перепроверок. Сортировку по индексу bitmap не сохраняет.

## 11–12. Отдельные и составной индексы

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [11-separate](plans/11-separate.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.37 | 0.095 | 2 | idx_orders_user_id |
| [12-composite](plans/12-composite.json) | Index Scan | 0.418 | 0.08 | 2 | idx_orders_user_status |

Индексы по user_id и status доступны одновременно в первом замере. В этом запуске выбран только idx_orders_user_id, BitmapAnd отсутствует. Для очень селективного user_id выгоднее найти несколько строк и отфильтровать status, чем строить bitmap четверти таблицы; наличие двух индексов не означает обязательный BitmapAnd. Во втором случае `(user_id,status)` задаёт оба равенства как границы поиска. Он полезен для такого сочетания, но отдельный status может обслуживать запросы без user_id. Поэтому универсального победителя нет: важны нагрузка, селективность, размер и цена обновления.

## 13. Порядок колонок

Каждый порядок проверялся отдельно: конкурирующие дополнительные индексы orders удалялись, PRIMARY KEY оставался.

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [13-user_created-1](plans/13-user_created-1.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.372 | 0.249 | 9 | idx_orders_user_created |
| [13-user_created-2](plans/13-user_created-2.json) | Index Scan | 0.345 | 0.051 | 1 | idx_orders_user_created |
| [13-user_created-3](plans/13-user_created-3.json) | Gather, Seq Scan | 0.349 | 64.342 | 41825 | — |
| [13-created_user-1](plans/13-created_user-1.json) | Gather, Seq Scan | 0.34 | 29.19 | 9 | — |
| [13-created_user-2](plans/13-created_user-2.json) | Index Scan | 0.345 | 2.809 | 1 | idx_orders_created_user |
| [13-created_user-3](plans/13-created_user-3.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.301 | 21.869 | 41825 | idx_orders_created_user |

Запрос 1 — user_id; 2 — user_id и последние 30 дней; 3 — только последние 30 дней. `(user_id,created_at)` оптимален для равенства по пользователю с последующим диапазоном дат; `(created_at,user_id)` ограничивает сначала временной диапазон и лучше обслуживает поиск только по дате. Условие только по второму столбцу обычно не задаёт узкий непрерывный диапазон B-tree. Возможности конкретной версии (включая skip scan в более новых версиях) не превращают эти индексы в одинаковые структуры.

## 14–15. ORDER BY и пагинация

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [14-sort-before](plans/14-sort-before.json) | Sort, Bitmap Heap Scan, Bitmap Index Scan | 0.347 | 0.178 | 9 | idx_orders_user_id |
| [14-sort-after](plans/14-sort-after.json) | Sort, Bitmap Heap Scan, Bitmap Index Scan | 0.38 | 0.18 | 9 | idx_orders_user_created_at_desc |
| [15-pagination-before](plans/15-pagination-before.json) | Limit, Sort, Bitmap Heap Scan, Bitmap Index Scan | 0.408 | 0.124 | 9 | idx_orders_user_id |
| [15-pagination-after](plans/15-pagination-after.json) | Limit, Sort, Bitmap Heap Scan, Bitmap Index Scan | 0.393 | 0.129 | 9 | idx_orders_user_created_at_desc |

Слева равенство user_id, далее created_at DESC позволяет отдавать строки в нужном порядке и остановиться на LIMIT 20. Однако при небольшом количестве заказов PostgreSQL может предпочесть bitmap плюс Sort: проверять нужно фактический план. Обычный индекс `(user_id,created_at)` также может обслужить DESC обратным проходом при фиксированном user_id; отдельный DESC-индекс не всегда нужен. В обоих замерах после создания индекса Sort сохранился: выбраны Bitmap Heap Scan и Bitmap Index Scan, а время почти не улучшилось. В этом раннем эксперименте у пользователя мало строк, поэтому ускорение не гарантировано; финальный эксперимент использует более активного пользователя.

## 16. Index Only Scan и INCLUDE

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [16-cover-before](plans/16-cover-before.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.316 | 0.107 | 9 | idx_orders_user_created_at_desc |
| [16-cover-after](plans/16-cover-after.json) | Index Only Scan | 0.328 | 0.087 | 9 | idx_orders_user_id_include |

Обычный индекс user_id не содержит выбранный id: PostgreSQL не добавляет PRIMARY KEY автоматически в каждый вторичный индекс. INCLUDE(id,status,created_at) покрывает проекцию. Для Index Only Scan нужны все используемые поля в индексе и подходящий метод доступа. Visibility map позволяет не читать heap только для all-visible страниц; после изменений возможны Heap Fetches даже при Index Only Scan. В эксперименте перед повторным запросом выполнен VACUUM (ANALYZE).

## 17. Частичный индекс

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [17-partial-before](plans/17-partial-before.json) | Sort, Bitmap Heap Scan, Bitmap Index Scan | 0.348 | 21.958 | 10000 | idx_orders_status |
| [17-partial-after](plans/17-partial-after.json) | Sort, Bitmap Heap Scan, Bitmap Index Scan | 0.348 | 14.515 | 10000 | idx_orders_new |

Здесь NEW составляет 1%: сначала используется обычный индекс status, затем он заменяется частичным `(created_at) WHERE status='NEW'`. Индекс хранит лишь нужные строки и способен поддержать порядок даты; в этом запуске выбран Bitmap Heap Scan с последующим Sort, а не упорядоченный Index Scan. Это уменьшает размер и обслуживание по сравнению с индексом на все строки, но подходит только запросам, из условий которых планировщик может вывести предикат NEW. Для PAID такой индекс не подходит. Параметризованный generic plan с неизвестным status тоже может не доказать применимость. [Размер оставшихся индексов](plans/17-index-size.txt).

## 18. Индекс по выражению

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [18-expression-before](plans/18-expression-before.json) | Seq Scan | 0.247 | 28.81 | 1 | — |
| [18-expression-after](plans/18-expression-after.json) | Index Scan | 0.312 | 0.057 | 1 | idx_users_lower_email |

users содержит 100001 строку, включая Test@Example.com, поэтому проверка не проводится на пустой таблице. Индекс email упорядочивает исходные строки, а не LOWER(email). Индекс по LOWER(email) соответствует выражению условия и находит одну строку. Важны совпадение выражения, типы, collation и неизменяемость индексируемой функции.

## 19. Цена INSERT

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [19-insert_plain](plans/19-insert_plain.json) | ModifyTable, Function Scan | 0.074 | 179.489 | 0 | — |
| [19-insert_indexed](plans/19-insert_indexed.json) | ModifyTable, Function Scan | 0.082 | 428.384 | 0 | — |

В обе изначально пустые таблицы вставляется одинаковый набор 100000 строк. В обеих есть PRIMARY KEY; во второй дополнительно три B-tree (user_id, status, created_at). Индексы orders не копируются. Для каждой строки PostgreSQL обновляет heap и все соответствующие индексы, выполняет поиск позиции, иногда расщепление страниц, создаёт WAL и грязные буферы. Это объясняет дополнительную работу при вставке. Сравнение единичное, без утверждения универсального коэффициента.

## 20. Использование индексов

[Снимок pg_stat_user_indexes](plans/20-usage.txt). Таблица ниже относится только к сохранившимся индексам: удалённые в контролируемых экспериментах индексы не появляются в итоговой статистике. Фактическое использование на каждом этапе подтверждается также Index Name в сохранённом плане. Счётчики могут обновляться с задержкой; idx_scan считает начатые сканирования, а не уникальные запросы. В итоговом снимке lab максимальный idx_scan=1 у idx_users_lower_email и idx_orders_paid_user_created; остальные сохранившиеся индексы имеют 0. У сервиса чаще всего использован частичный индекс (2), общий и PK — по 1. Нулевой счётчик за короткий тест не доказывает бесполезность индекса: он может поддерживать уникальность, редкие операции и внешние ключи, либо статистика была сброшена. Перед удалением нужны длительное наблюдение, проверка ограничений и планы важных запросов. Риски — деградация чтений, блокировки DDL, потеря уникальности при удалении ограничения.

## 21. Финальный запрос

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [21-final-before](plans/21-final-before.json) | Limit, Gather Merge, Sort, Seq Scan | 0.331 | 33.369 | 50 | — |
| [21-final-after](plans/21-final-after.json) | Limit, Index Only Scan | 0.38 | 0.087 | 50 | idx_orders_paid_user_created |

В этом запуске: 33.369 → 0.087 мс; отношение времени до/после = 383.55. Это единичный замер, не статистическая оценка ускорения.

Реальный SQL с user_id=123 вместо $1 сохранён в results.json. До оптимизации нет дополнительных индексов orders: фильтрация и сортировка могут читать таблицу целиком. Выбран частичный покрывающий индекс `(user_id,created_at DESC) INCLUDE(id,amount,status) WHERE status='PAID'`. Сначала равенство пользователя, затем диапазон и порядок даты; статус PAID фиксируется предикатом, возвращаемые поля покрыты INCLUDE. Индекс не содержит NOW() в предикате: скользящее время не является immutable. После VACUUM он может отдавать до 50 строк без чтения heap и явной сортировки. В production необходимо отдельно проверить generic/custom plans параметризованных запросов и распределение пользователей.

## 22. Собственный учебный сервис и Scaling Entity

По согласованию создан новый сервис заказов: исходный репозиторий пустой, существующих endpoint и production-логов не было. Это честная модель собственного проекта, не анализ вымышленной действующей системы. Реализация: [server.py](../scripts/server.py); схема [001_orders.sql](../migrations/001_orders.sql).

Scaling Entity — `service.orders`, история покупок пользователей. Каждая покупка добавляет запись, а справочные сущности меняются реже. Плановый сценарий: 1000 заказов/день, около 365000 новых заказов/год без удаления; это допущение для оценки нагрузки, не измеренный прогноз. Основные поля поиска: user_id, status, created_at. PK id нужен для идентификации и стабильного порядка при равных датах.

## 23–24. Три запроса и базовые измерения

Query 1 — все заказы пользователя; Query 2 — его PAID-заказы; Query 3 — фактический запрос endpoint `/users/123/orders?status=PAID&days=30&limit=50`. Первые два — диагностические выборки на основе этого endpoint; третий создаётся непосредственно функцией orders_query, используемой сервером. SQL всех запросов сохранён в service-results.json; отдельные обычные EXPLAIN — в service-query*-explain.txt.

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [service-query1-before](plans/service-query1-before.json) | Gather, Seq Scan | 0.237 | 28.748 | 1009 | — |
| [service-query2-before](plans/service-query2-before.json) | Gather, Seq Scan | 0.27 | 22.818 | 1005 | — |
| [service-query3-before](plans/service-query3-before.json) | Limit, Gather Merge, Sort, Seq Scan | 0.279 | 25.397 | 50 | — |

## 25–26. Индексы и проблемы

До оптимизации есть только orders_pkey(id), который не обслуживает фильтрацию user_id. [Определения до](plans/service-indexes-before.txt), [определения и статистика после](plans/service-indexes-after.txt).

Во всех трёх запросах совпадает малая доля миллиона строк, но без дополнительного индекса приходится проверять всю таблицу. Для Query 1 достаточно префикса user_id; для Query 2 полезен user_id с предикатом PAID; Query 3 также нуждается в порядке даты и раннем LIMIT. Переписывание SQL без индекса не устраняет полное чтение; проекция нужных полей уменьшает передачу и позволяет покрывающий индекс. Тяжёлую неограниченную выдачу в реальном API следует заменять пагинацией; здесь Query 1/2 служат диагностике. Для продолжения страниц рекомендуется keyset по `(created_at,id)` вместо растущего OFFSET.

## 27–29. Миграция и повторное измерение

[002_indexes.sql](../migrations/002_indexes.sql) добавляет общий покрывающий `(user_id,created_at DESC,id DESC) INCLUDE(amount,status)` для выдачи заказов пользователя и частичный аналог для PAID. Общий индекс нужен запросам без статуса; частичный меньше при редком PAID и точнее соответствует фильтрованной выдаче. В текущей синтетической выборке PAID доминирует после изменения распределения для задания 17, поэтому преимущество частичного размера ограничено. Поддержка обоих — осознанный учебный компромисс; в production необходимость обоих нужно подтвердить нагрузкой и ценой записи.

| Замер | Scan / узлы | Planning, мс | Execution, мс | Actual Rows корня | Индекс |
|---|---|---:|---:|---:|---|
| [service-query1-before](plans/service-query1-before.json) | Gather, Seq Scan | 0.237 | 28.748 | 1009 | — |
| [service-query1-after](plans/service-query1-after.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.369 | 2.564 | 1009 | idx_service_orders_user_created |
| [service-query2-before](plans/service-query2-before.json) | Gather, Seq Scan | 0.27 | 22.818 | 1005 | — |
| [service-query2-after](plans/service-query2-after.json) | Bitmap Heap Scan, Bitmap Index Scan | 0.342 | 2.41 | 1005 | idx_service_orders_paid_user_created |
| [service-query3-before](plans/service-query3-before.json) | Limit, Gather Merge, Sort, Seq Scan | 0.279 | 25.397 | 50 | — |
| [service-query3-after](plans/service-query3-after.json) | Limit, Index Only Scan | 0.388 | 0.211 | 50 | idx_service_orders_paid_user_created |

Миграции применяются транзакционно, версии записываются в schema_migrations. Повторный запуск проверен: уже применённые миграции пропускаются. Измерение до снято после 001, после — после 002 и VACUUM ANALYZE. Ошибки миграций останавливают процесс. Для живой нагруженной базы обычный CREATE INDEX может блокировать запись: production-развёртывание потребует отдельно спроектированной нетранзакционной миграции CONCURRENTLY.

Функциональная проверка `scripts/smoke.py` проверяет реальный HTTP и БД: health, ровно 50 PAID-заказов пользователя за 30 дней, порядок даты/id, пустую выдачу, неверные параметры и неизвестный маршрут. Результат запуска сохранён в [validation.txt](plans/validation.txt). Это read-only учебный сервис; создание заказов, авторизация и полноценный production connection pool в объём лабораторной не входят.

## 30. Почему нельзя индексировать всё

Каждый индекс занимает дисковое пространство, увеличивает резервные копии, WAL и нагрузку на кеш. INSERT добавляет индексные записи; UPDATE индексируемых полей создаёт новые версии и может лишать HOT-update; изменение включённых INCLUDE полей тоже требует обслуживания. DELETE оставляет мёртвые версии, которые позже убирает VACUUM, поэтому удаление также увеличивает работу и может вызывать разрастание. Индексы замедляют запись и требуют обслуживания даже при редком использовании на чтении. Разные порядок колонок, выражения и предикаты обслуживают разные запросы, поэтому набор «на каждую колонку» не заменяет проектирование под реальные условия и сортировку. Решение принимается по планам, измерениям, статистике нагрузки, ограничениям целостности и допустимой стоимости хранения и записи.

## Детализация начального сканирования

- Seq Scan: estimated rows=5, actual rows=3, loops=3, Rows Removed by Filter=333330 (в среднем на loop).

## Снимки использования индексов

```text

lab|orders|orders_pkey|0
lab|users|users_pkey|0
lab|users|idx_users_email|0
lab|insert_indexed|ins_status|0
lab|insert_indexed|ins_created|0
lab|insert_plain|insert_plain_pkey|0
lab|insert_indexed|insert_indexed_pkey|0
lab|insert_indexed|ins_user|0
lab|users|idx_users_lower_email|1
lab|orders|idx_orders_paid_user_created|1
```

Сервис после измерений:

```text
orders_pkey|CREATE UNIQUE INDEX orders_pkey ON service.orders USING btree (id)
idx_service_orders_user_created|CREATE INDEX idx_service_orders_user_created ON service.orders USING btree (user_id, created_at DESC, id DESC) INCLUDE (amount, status)
idx_service_orders_paid_user_created|CREATE INDEX idx_service_orders_paid_user_created ON service.orders USING btree (user_id, created_at DESC, id DESC) INCLUDE (amount, status) WHERE ((status)::text = 'PAID'::text)

orders_pkey|1
idx_service_orders_user_created|1
idx_service_orders_paid_user_created|2```
