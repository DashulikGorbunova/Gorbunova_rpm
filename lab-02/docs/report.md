# Лабораторная №2. Когда индексов недостаточно

## Методика и ограничения

Реальные замеры PostgreSQL 17 в выделенном Docker-контейнере, 2 ноября 2026 г. [Окружение и настройки](plans/environment.json). Отдельная схема `lab02`; данные первой работы не затрагиваются. Генерация детерминированная: user_id и время распределены модульной арифметикой, даты относительно сохранённого anchor, категории событий 40/30/20/10%. Это синтетическая модель, без production-трафика и перекоса популярных пользователей. После загрузки выполняется ANALYZE, перед покрывающими сканированиями — VACUUM ANALYZE. Планировщик не принуждается использовать индекс.

Каждый запрос измерен три раза подряд, в таблицах медиана Execution Time. Все планы включают ANALYZE и BUFFERS. Это преимущественно прогретый кеш, без перезапуска PostgreSQL и конкурентной нагрузки. Время передачи результатов клиенту не входит в Execution Time. Для параллельных планов actual rows и Rows Removed by Filter — средние на loop; для оценки работы нужно учитывать loops, округление может влиять на сумму. Размеры в MiB (1024² байт). Дополнительные 10 млн не исследовались: обязательные точки до 5 млн выполнены; 100 млн обсуждаются как теоретический сценарий.

## A. 1–3. Таблица, данные и размеры

```sql
CREATE TABLE events (
 id BIGSERIAL PRIMARY KEY, user_id BIGINT NOT NULL,
 event_type VARCHAR(50) NOT NULL, payload JSONB,
 created_at TIMESTAMP NOT NULL
);
```

Генератор generate_series и точные формулы: [experiments.py](../scripts/experiments.py). На каждой точке таблица загружается заново, сначала существует только PK; затем последовательно добавляются три дополнительных индекса.

| Строк | Heap MiB | Всего с PK MiB | Всего с тремя индексами и PK MiB |
|---:|---:|---:|---:|
| 10000 | 0.66 | 0.92 | 1.71 |
| 100000 | 6.52 | 8.70 | 16.05 |
| 1000000 | 65.11 | 86.60 | 147.20 |
| 5000000 | 325.52 | 432.76 | 724.43 |

Размеры получены через pg_relation_size, pg_total_relation_size и pg_indexes_size; сырые байты сохранены в [sizes.json](plans/sizes.json).

## A. 4–5. Поиск пользователя

```sql
SELECT * FROM events WHERE user_id=123;
```

| Измерение | мс (медиана) | Scan / операции | Индекс | actual rows × loops; removed × loops |
|---|---:|---|---|---|
| [a-10000-user-before](plans/a-10000-user-before.json) | 1.114 | Seq Scan | — | 0 × 1; 10000 × 1 |
| [a-10000-user-after](plans/a-10000-user-after.json) | 0.070 | Index Scan | idx_events_user_id | 0 × 1; 0 × 1 |
| [a-100000-user-before](plans/a-100000-user-before.json) | 9.842 | Seq Scan | — | 1 × 1; 99999 × 1 |
| [a-100000-user-after](plans/a-100000-user-after.json) | 0.079 | Index Scan | idx_events_user_id | 1 × 1; 0 × 1 |
| [a-1000000-user-before](plans/a-1000000-user-before.json) | 85.578 | Gather, Seq Scan | — | 3 × 3; 333330 × 3 |
| [a-1000000-user-after](plans/a-1000000-user-after.json) | 0.317 | Bitmap Heap Scan, Bitmap Index Scan | idx_events_user_id | 10 × 1; 0 × 1; 10 × 1; 0 × 1 |
| [a-5000000-user-before](plans/a-5000000-user-before.json) | 263.224 | Gather, Seq Scan | — | 17 × 3; 1666650 × 3 |
| [a-5000000-user-after](plans/a-5000000-user-after.json) | 0.365 | Bitmap Heap Scan, Bitmap Index Scan | idx_events_user_id | 50 × 1; 0 × 1; 50 × 1; 0 × 1 |

| Строк | Без индекса мс | С индексом мс | Ускорение |
|---:|---:|---:|---:|
| 10000 | 1.114 | 0.070 | 15.9× |
| 100000 | 9.842 | 0.079 | 124.6× |
| 1000000 | 85.578 | 0.317 | 270.0× |
| 5000000 | 263.224 | 0.365 | 721.2× |

Без дополнительного индекса проверяется вся таблица; работа растёт с объёмом. Индекс `idx_events_user_id(user_id)` добавляет Index Cond и позволяет получить только совпадения. Разница заметна уже на 100k; точный коэффициент зависит от кеша. На очень маленькой таблице или при высокой доле совпадений Seq Scan может быть дешевле.

## A. 6. Диапазон дат

```sql
SELECT * FROM events WHERE created_at >= NOW()-INTERVAL '1 day';
```

| Измерение | мс (медиана) | Scan / операции | Индекс | actual rows × loops; removed × loops |
|---|---:|---|---|---|
| [a-10000-day-before](plans/a-10000-day-before.json) | 6.766 | Seq Scan | — | 27 × 1; 9973 × 1 |
| [a-10000-day-after](plans/a-10000-day-after.json) | 0.136 | Bitmap Heap Scan, Bitmap Index Scan | idx_events_created_at | 27 × 1; 0 × 1; 27 × 1; 0 × 1 |
| [a-10000-wide-before](plans/a-10000-wide-before.json) | 3.988 | Seq Scan | — | 10000 × 1; 0 × 1 |
| [a-10000-wide-after](plans/a-10000-wide-after.json) | 5.787 | Seq Scan | — | 10000 × 1; 0 × 1 |
| [a-100000-day-before](plans/a-100000-day-before.json) | 28.310 | Seq Scan | — | 266 × 1; 99734 × 1 |
| [a-100000-day-after](plans/a-100000-day-after.json) | 1.532 | Bitmap Heap Scan, Bitmap Index Scan | idx_events_created_at | 266 × 1; 0 × 1; 266 × 1; 0 × 1 |
| [a-100000-wide-before](plans/a-100000-wide-before.json) | 42.342 | Seq Scan | — | 100000 × 1; 0 × 1 |
| [a-100000-wide-after](plans/a-100000-wide-after.json) | 41.918 | Seq Scan | — | 100000 × 1; 0 × 1 |
| [a-1000000-day-before](plans/a-1000000-day-before.json) | 289.463 | Gather, Seq Scan | — | 912 × 3; 332422 × 3 |
| [a-1000000-day-after](plans/a-1000000-day-after.json) | 25.462 | Bitmap Heap Scan, Bitmap Index Scan | idx_events_created_at | 2734 × 1; 0 × 1; 2734 × 1; 0 × 1 |
| [a-1000000-wide-before](plans/a-1000000-wide-before.json) | 903.850 | Seq Scan | — | 1000000 × 1; 0 × 1 |
| [a-1000000-wide-after](plans/a-1000000-wide-after.json) | 761.605 | Seq Scan | — | 999999 × 1; 1 × 1 |
| [a-5000000-day-before](plans/a-5000000-day-before.json) | 956.508 | Gather, Seq Scan | — | 4562 × 3; 1662105 × 3 |
| [a-5000000-day-after](plans/a-5000000-day-after.json) | 120.817 | Bitmap Heap Scan, Bitmap Index Scan | idx_events_created_at | 13682 × 1; 0 × 1; 13682 × 1; 0 × 1 |
| [a-5000000-wide-before](plans/a-5000000-wide-before.json) | 1969.063 | Seq Scan | — | 4999987 × 1; 13 × 1 |
| [a-5000000-wide-after](plans/a-5000000-wide-after.json) | 2001.043 | Seq Scan | — | 4999985 × 1; 15 × 1 |


Индекс `idx_events_created_at(created_at)` отсекает большую часть строк для суток (~1/365 данных). За год возвращается практически вся таблица: чтение heap и большой результат остаются; индекс может потребовать дополнительных случайных чтений. Поэтому широкий диапазон сравнивается отдельно, а Seq Scan является обоснованным выбором.

## A. 7. Фильтрация и сортировка

```sql
SELECT * FROM events WHERE user_id=123 ORDER BY created_at DESC LIMIT 100;
```

| Измерение | мс (медиана) | Scan / операции | Индекс | actual rows × loops; removed × loops |
|---|---:|---|---|---|
| [a-10000-sort-before](plans/a-10000-sort-before.json) | 0.073 | Limit, Sort, Index Scan | idx_events_user_id | 0 × 1; 0 × 1 |
| [a-10000-sort-after](plans/a-10000-sort-after.json) | 0.045 | Limit, Index Scan | idx_events_user_created | 0 × 1; 0 × 1 |
| [a-100000-sort-before](plans/a-100000-sort-before.json) | 0.094 | Limit, Sort, Index Scan | idx_events_user_id | 1 × 1; 0 × 1 |
| [a-100000-sort-after](plans/a-100000-sort-after.json) | 0.073 | Limit, Sort, Index Scan | idx_events_user_id | 1 × 1; 0 × 1 |
| [a-1000000-sort-before](plans/a-1000000-sort-before.json) | 0.184 | Limit, Sort, Bitmap Heap Scan, Bitmap Index Scan | idx_events_user_id | 10 × 1; 0 × 1; 10 × 1; 0 × 1 |
| [a-1000000-sort-after](plans/a-1000000-sort-after.json) | 0.731 | Limit, Sort, Bitmap Heap Scan, Bitmap Index Scan | idx_events_user_created | 10 × 1; 0 × 1; 10 × 1; 0 × 1 |
| [a-5000000-sort-before](plans/a-5000000-sort-before.json) | 0.576 | Limit, Sort, Bitmap Heap Scan, Bitmap Index Scan | idx_events_user_id | 50 × 1; 0 × 1; 50 × 1; 0 × 1 |
| [a-5000000-sort-after](plans/a-5000000-sort-after.json) | 0.285 | Limit, Sort, Bitmap Heap Scan, Bitmap Index Scan | idx_events_user_created | 50 × 1; 0 × 1; 50 × 1; 0 × 1 |


До составного индекса PostgreSQL получает строки по user_id и сортирует их. `idx_events_user_created(user_id,created_at DESC)` может обслужить равенство и порядок без Sort и допускает раннюю остановку LIMIT. На 10k у пользователя 123 нет совпадений (actual rows=0): Sort отсутствует, но это не доказательство выигрыша на непустой выдаче. На 100k, 1 млн и 5 млн планировщик сохранил Sort: наличие подходящего составного индекса не обязывает выбирать его. На этих данных у пользователя только 50 строк на 5 млн: выигрыш ограничен малой сортировкой; фактический план 5 млн приведён в таблице. Отключение scan-методов ради желаемого результата не применялось. Обратный порядок колонок сначала упорядочивал бы всех пользователей по дате и не давал бы компактного диапазона одного пользователя.

## A. 8. Агрегация

```sql
SELECT event_type,COUNT(*) FROM events WHERE created_at>=NOW()-INTERVAL '30 days' GROUP BY event_type;
```

| Измерение | мс (медиана) | Scan / операции | Индекс | actual rows × loops; removed × loops |
|---|---:|---|---|---|
| [a-10000-aggregate-before](plans/a-10000-aggregate-before.json) | 6.012 | Aggregate, Seq Scan | — | 840 × 1; 9160 × 1 |
| [a-10000-aggregate-after](plans/a-10000-aggregate-after.json) | 0.479 | Aggregate, Bitmap Heap Scan, Bitmap Index Scan | idx_events_created_at | 840 × 1; 0 × 1; 840 × 1; 0 × 1 |
| [a-100000-aggregate-before](plans/a-100000-aggregate-before.json) | 31.150 | Aggregate, Seq Scan | — | 8232 × 1; 91768 × 1 |
| [a-100000-aggregate-after](plans/a-100000-aggregate-after.json) | 5.330 | Aggregate, Bitmap Heap Scan, Bitmap Index Scan | idx_events_created_at | 8232 × 1; 0 × 1; 8232 × 1; 0 × 1 |
| [a-1000000-aggregate-before](plans/a-1000000-aggregate-before.json) | 377.397 | Aggregate, Gather Merge, Sort, Seq Scan | — | 27396 × 3; 305937 × 3 |
| [a-1000000-aggregate-after](plans/a-1000000-aggregate-after.json) | 51.938 | Aggregate, Gather Merge, Sort, Bitmap Heap Scan, Bitmap Index Scan | idx_events_created_at | 27396 × 3; 0 × 3; 82188 × 1; 0 × 1 |
| [a-5000000-aggregate-before](plans/a-5000000-aggregate-before.json) | 961.312 | Aggregate, Gather Merge, Sort, Seq Scan | — | 136984 × 3; 1529683 × 3 |
| [a-5000000-aggregate-after](plans/a-5000000-aggregate-after.json) | 275.186 | Aggregate, Gather Merge, Sort, Bitmap Heap Scan, Bitmap Index Scan | idx_events_created_at | 136983 × 3; 0 × 3; 410948 × 1; 0 × 1 |


Узлы Aggregate/HashAggregate и возможные Gather/Sort показаны в таблице и планах. Месячный интервал выбирает около 30/365 таблицы (~411 тысяч строк на 5 млн). Индекс помогает найти диапазон, но event_type нужно получить из heap, затем каждую выбранную строку включить в COUNT. Полностью убрать стоимость агрегации индекс по дате не может.

## A. 9. Цена INSERT и UPDATE

Одинаковый пакет из 100000 новых строк вставляется в таблицу с 5 млн строк: сначала только PK, затем PK и три требуемых индекса. UPDATE меняет индексируемые user_id и created_at у id≤100000. Каждый EXPLAIN ANALYZE действительно выполняет запись, после чего транзакция откатывается, а VACUUM освобождает мёртвые версии. Поэтому логическая исходная мощность одинакова; физический размер/кеш после откатов могут отличаться. Последовательности в пакетной вставке не используются (id задан явно).

| Измерение | мс (медиана) | Scan / операции | Индекс | actual rows × loops; removed × loops |
|---|---:|---|---|---|
| [a-write-insert-before](plans/a-write-insert-before.json) | 315.827 | ModifyTable, Seq Scan, Function Scan | — | 1 × 1; 0 × 1; 100000 × 1; 0 × 1 |
| [a-write-insert-after](plans/a-write-insert-after.json) | 3959.623 | ModifyTable, Seq Scan, Function Scan | — | 1 × 1; 0 × 1; 100000 × 1; 0 × 1 |
| [a-write-update-before](plans/a-write-update-before.json) | 557.133 | ModifyTable, Index Scan | events_pkey | 100000 × 1; 0 × 1 |
| [a-write-update-after](plans/a-write-update-after.json) | 2074.780 | ModifyTable, Index Scan | events_pkey | 100000 × 1; 0 × 1 |


Каждая вставленная строка добавляет запись во все B-tree, генерирует WAL, загрязняет страницы и иногда вызывает их расщепление. Изменение индексируемых полей при UPDATE требует новых индексных записей и препятствует HOT. Откат не отменяет уже потраченную работу и WAL. Индексы на каждой колонке увеличивают запись, хранение и обслуживание; выбирать их нужно под реальные запросы.

## A. 10. Размеры индексов

| Строк | Индекс | MiB |
|---:|---|---:|
| 10000 | events_pkey | 0.23 |
| 10000 | idx_events_created_at | 0.23 |
| 10000 | idx_events_user_created | 0.32 |
| 10000 | idx_events_user_id | 0.23 |
| 100000 | events_pkey | 2.16 |
| 100000 | idx_events_created_at | 2.16 |
| 100000 | idx_events_user_created | 3.03 |
| 100000 | idx_events_user_id | 2.16 |
| 1000000 | events_pkey | 21.45 |
| 1000000 | idx_events_created_at | 21.45 |
| 1000000 | idx_events_user_created | 30.10 |
| 1000000 | idx_events_user_id | 9.04 |
| 5000000 | events_pkey | 107.12 |
| 5000000 | idx_events_created_at | 107.13 |
| 5000000 | idx_events_user_created | 150.42 |
| 5000000 | idx_events_user_id | 34.11 |

Размер измерен через pg_stat_user_indexes и pg_relation_size(indexrelid), до эксперимента записи. Он растёт вместе с числом записей, зависит от ширины ключа, дедупликации и заполнения страниц. Составной индекс хранит два ключа и обычно больше одиночного; размер не обязан быть строго линейным.

## A. 11. Сто миллионов событий

```sql
SELECT DATE(created_at), COUNT(*) FROM events
WHERE created_at >= NOW()-INTERVAL '365 days'
GROUP BY DATE(created_at);
```

При годовом хранении это почти 100 млн входных строк. Даже Index Only Scan должен прочесть множество индексных страниц, проверить видимость и агрегировать строки; обычный индекс требует также heap. Небольшой результат (~365 групп) не означает небольшую работу. Этот объём не измерялся. Варианты: дневные агрегаты или materialized view с инкрементальным обновлением, уменьшение диапазона, кеширование, архив/retention, партиционирование по дате для pruning и удаления старых данных, аналитическая реплика/колоночная система. Партиционирование не устраняет чтение всех нужных годовых партиций.

## B. 12–14. Сущность, SQL и baseline

Выбрана `orders` существующего учебного сервиса первой работы. В сохранённых замерах lab-01 было 1 млн синтетических заказов; в новой изолированной схеме перед генерацией 0. Доступа к production-базе нет. История покупок накапливается с каждой покупкой; рабочее допущение первой работы — 1000 заказов/день (365k/год), не измеренный прогноз.

Точная схема и два индекса импортированы из миграций lab-01. Q1 и Q3 формируются реальной функцией `orders_query` HTTP-сервера. Q2 — диагностический диапазон для отчёта по заказам, не отдельный существующий endpoint; это явно выбранный аналитический сценарий на сущности сервиса. В lab02 10000 пользователей, равномерное распределение. Baseline имеет только PK; existing — оба индекса из первой работы; optimized — дополнительно покрывающий индекс даты.

| Заказов | Heap MiB | Всего с PK MiB | Всего после оптимизации MiB |
|---:|---:|---:|---:|
| 100000 | 8.30 | 10.48 | 23.64 |
| 1000000 | 83.02 | 104.50 | 235.38 |
| 5000000 | 415.06 | 522.31 | 1176.23 |

| Заказов | Индекс | MiB |
|---:|---|---:|
| 100000 | idx_orders_created_cover | 5.01 |
| 100000 | idx_service_orders_paid_user_created | 2.27 |
| 100000 | idx_service_orders_user_created | 5.88 |
| 100000 | orders_pkey | 2.16 |
| 1000000 | idx_orders_created_cover | 49.84 |
| 1000000 | idx_service_orders_paid_user_created | 22.46 |
| 1000000 | idx_service_orders_user_created | 58.58 |
| 1000000 | orders_pkey | 21.45 |
| 5000000 | idx_orders_created_cover | 249.09 |
| 5000000 | idx_service_orders_paid_user_created | 112.18 |
| 5000000 | idx_service_orders_user_created | 292.62 |
| 5000000 | orders_pkey | 107.12 |

### q1

```sql
SELECT id,amount,status,created_at FROM lab02.orders WHERE user_id=123 ORDER BY created_at DESC,id DESC LIMIT 100;
```


### q2

```sql
SELECT id,amount,status,created_at FROM orders WHERE created_at>=NOW()-INTERVAL '30 days' AND created_at<NOW();
```


### q3

```sql
SELECT id,amount,status,created_at FROM lab02.orders WHERE user_id=123 AND status='PAID' AND created_at>=NOW()-30*INTERVAL '1 day' ORDER BY created_at DESC,id DESC LIMIT 50;
```

## B. 15–16. Рост и сравнение

| Измерение | мс (медиана) | Scan / операции | Индекс | actual rows × loops; removed × loops |
|---|---:|---|---|---|
| [b-100000-q1-baseline](plans/b-100000-q1-baseline.json) | 11.304 | Limit, Sort, Seq Scan | — | 10 × 1; 99990 × 1 |
| [b-100000-q1-existing](plans/b-100000-q1-existing.json) | 0.175 | Limit, Index Only Scan | idx_service_orders_user_created | 10 × 1; 0 × 1 |
| [b-100000-q1-optimized](plans/b-100000-q1-optimized.json) | 0.097 | Limit, Index Only Scan | idx_service_orders_user_created | 10 × 1; 0 × 1 |
| [b-100000-q2-baseline](plans/b-100000-q2-baseline.json) | 36.161 | Seq Scan | — | 8231 × 1; 91769 × 1 |
| [b-100000-q2-existing](plans/b-100000-q2-existing.json) | 46.063 | Seq Scan | — | 8231 × 1; 91769 × 1 |
| [b-100000-q2-optimized](plans/b-100000-q2-optimized.json) | 8.072 | Index Only Scan | idx_orders_created_cover | 8231 × 1; 0 × 1 |
| [b-100000-q3-baseline](plans/b-100000-q3-baseline.json) | 14.750 | Limit, Sort, Seq Scan | — | 0 × 1; 100000 × 1 |
| [b-100000-q3-existing](plans/b-100000-q3-existing.json) | 0.095 | Limit, Index Only Scan | idx_service_orders_paid_user_created | 0 × 1; 0 × 1 |
| [b-100000-q3-optimized](plans/b-100000-q3-optimized.json) | 0.060 | Limit, Index Only Scan | idx_service_orders_paid_user_created | 0 × 1; 0 × 1 |
| [b-1000000-q1-baseline](plans/b-1000000-q1-baseline.json) | 49.831 | Limit, Gather Merge, Sort, Seq Scan | — | 33 × 3; 333300 × 3 |
| [b-1000000-q1-existing](plans/b-1000000-q1-existing.json) | 0.120 | Limit, Index Only Scan | idx_service_orders_user_created | 100 × 1; 0 × 1 |
| [b-1000000-q1-optimized](plans/b-1000000-q1-optimized.json) | 0.093 | Limit, Index Only Scan | idx_service_orders_user_created | 100 × 1; 0 × 1 |
| [b-1000000-q2-baseline](plans/b-1000000-q2-baseline.json) | 176.344 | Gather, Seq Scan | — | 27395 × 3; 305939 × 3 |
| [b-1000000-q2-existing](plans/b-1000000-q2-existing.json) | 218.624 | Gather, Seq Scan | — | 27395 × 3; 305939 × 3 |
| [b-1000000-q2-optimized](plans/b-1000000-q2-optimized.json) | 15.672 | Index Only Scan | idx_orders_created_cover | 82184 × 1; 0 × 1 |
| [b-1000000-q3-baseline](plans/b-1000000-q3-baseline.json) | 62.664 | Limit, Gather Merge, Sort, Seq Scan | — | 0 × 3; 333333 × 3 |
| [b-1000000-q3-existing](plans/b-1000000-q3-existing.json) | 0.088 | Limit, Index Only Scan | idx_service_orders_paid_user_created | 1 × 1; 0 × 1 |
| [b-1000000-q3-optimized](plans/b-1000000-q3-optimized.json) | 0.093 | Limit, Index Only Scan | idx_service_orders_paid_user_created | 1 × 1; 0 × 1 |
| [b-5000000-q1-baseline](plans/b-5000000-q1-baseline.json) | 194.993 | Limit, Gather Merge, Sort, Seq Scan | — | 167 × 3; 1666500 × 3 |
| [b-5000000-q1-existing](plans/b-5000000-q1-existing.json) | 0.137 | Limit, Index Only Scan | idx_service_orders_user_created | 100 × 1; 0 × 1 |
| [b-5000000-q1-optimized](plans/b-5000000-q1-optimized.json) | 0.197 | Limit, Index Only Scan | idx_service_orders_user_created | 100 × 1; 0 × 1 |
| [b-5000000-q2-baseline](plans/b-5000000-q2-baseline.json) | 819.837 | Gather, Seq Scan | — | 136977 × 3; 1529689 × 3 |
| [b-5000000-q2-existing](plans/b-5000000-q2-existing.json) | 749.378 | Gather, Seq Scan | — | 136977 × 3; 1529690 × 3 |
| [b-5000000-q2-optimized](plans/b-5000000-q2-optimized.json) | 164.218 | Index Only Scan | idx_orders_created_cover | 410930 × 1; 0 × 1 |
| [b-5000000-q3-baseline](plans/b-5000000-q3-baseline.json) | 229.303 | Limit, Gather Merge, Sort, Seq Scan | — | 5 × 3; 1666662 × 3 |
| [b-5000000-q3-existing](plans/b-5000000-q3-existing.json) | 0.184 | Limit, Index Only Scan | idx_service_orders_paid_user_created | 15 × 1; 0 × 1 |
| [b-5000000-q3-optimized](plans/b-5000000-q3-optimized.json) | 0.091 | Limit, Index Only Scan | idx_service_orders_paid_user_created | 15 × 1; 0 × 1 |

## B. 17–19. Узкое место и граница индексов

```sql
SELECT id,amount,status,created_at FROM orders WHERE created_at>=NOW()-INTERVAL '30 days' AND created_at<NOW();
```

Q2 возвращает все заказы за 30 дней: при 5 млн требуется обработать около 411 тысяч записей. Индексы пользователя не дают ведущего ключа даты. [План до](plans/b-5000000-q2-existing.json) показывает исходное чтение; [план после](plans/b-5000000-q2-optimized.json) фиксирует результат оптимизации.

```sql
CREATE INDEX idx_orders_created_cover
ON lab02.orders(created_at) INCLUDE(id,amount,status);
VACUUM (ANALYZE) lab02.orders;
```

На 5 млн время Q2 изменилось с 749.378 до 164.218 мс. После оптимизации на 1 млн было 15.672 мс: рост количества совпадений продолжает увеличивать стоимость. В отличие от ограниченных Q1/Q3, диапазон Q2 не имеет LIMIT. Покрывающий индекс уменьшает heap-чтения, но не число возвращаемых строк и сетевой объём. Это измеренная граница для данного сценария: индекс улучшает доступ, однако не обеспечивает постоянную стоимость неограниченной месячной выдачи. Универсальный порог в миллионах или нарушение SLA из этих опытов вывести нельзя: SLA не задан, 100 млн не измерялись.

Для пользовательского интерфейса нужна keyset-пагинация (created_at,id) и соответствующий индекс; для итогов по периоду — предагрегация вместо выдачи всех строк; для выгрузок — асинхронная обработка. Нельзя заменить полную выгрузку LIMIT без изменения требований к результату. Покрывающий индекс добавляет хранение и обслуживание amount/status, поэтому его полезность зависит от доли аналитического чтения и записи.

## Контрольные вопросы

1. Seq Scan хорош, когда нужна значительная часть таблицы или таблица мала: последовательное чтение дешевле множества обращений к heap.
2. Индекс могут не выбрать из-за низкой селективности, стоимости random I/O, несовпадения выражения/предиката/порядка ключей или неточной статистики.
3. INSERT добавляет ключ и указатель на версию строки в каждый подходящий индекс, иногда разделяет страницу.
4. Больше индексов — больше WAL, CPU, грязных страниц и обслуживания при записи.
5. Селективность условия — доля подходящих строк; малая доля означает более избирательный поиск.
6. Индекс быстро локализует небольшой диапазон ключей, сокращая прочитанные данные.
7. При большой доле совпадений поиск и чтение heap через индекс могут стоить дороже полного прохода.
8. EXPLAIN ANALYZE выполняет запрос и показывает фактические времена, строки и loops; для записей нужны отдельная база/транзакция.
9. Rows Removed by Filter — строки, прочитанные узлом и отброшенные его фильтром, в среднем на loop.
10. Index Cond — условие доступа по индексу; Filter проверяется после получения кандидатов.
11. Index Scan получает heap-строки через индекс по мере обхода; Bitmap Index Scan строит карту TID для последующего Bitmap Heap Scan по страницам.
12. В B-tree ведущие равенства задают компактный диапазон, следующие ключи — диапазон/порядок; перестановка меняет доступные пути.
13. GROUP BY должен обработать все входящие совпадения, даже когда индекс ускорил их поиск.
14. ANALYZE обновляет статистику распределения и оценку строк; ошибки оценок ведут к неудачному выбору scan/join/aggregate.
15. Растут heap, индексы, объём чтения, давление на кеш и цена записи; эффект зависит от селективности и LIMIT.
16. Индексы всех колонок не заменяют составные/частичные ключи и увеличивают стоимость записи и хранения.
17. pg_relation_size показывает основную relation; pg_total_relation_size добавляет индексы, TOAST и служебные части.
18. pg_relation_size(indexrelid) из pg_stat_user_indexes даёт размер конкретного индекса; pg_indexes_size — всех индексов таблицы.
