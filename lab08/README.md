# Практическая №8 — SSR-витрина «Сириус.Еды»
Горбунова Дарья. Вариант Б (с нуля), бонус SEO + ISR, CSR для сравнения.

## Запуск на macOS
Node.js 20.9+, npm 10+, Python и Docker. Используется backend lab-06 без изменения его файлов: адаптер открывает только публичные GET меню и добавляет GET одного блюда; запись остаётся защищённой JWT. Redis и PostgreSQL — из lab-06.

```bash
cd lab-06
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
# Только если .env ещё нет:
python scripts/init_env.py
docker compose up -d --wait db redis
alembic upgrade head
cd ../lab08
python backend/seed.py
python -m uvicorn backend.public_api:app --host 127.0.0.1 --port 8000
```

В отдельном терминале из lab08:
```bash
npm install
cp .env.example .env.local
npm run dev
```
Открыть http://localhost:3000. В lab-06/.env должен быть ALLOWED_ORIGINS=["http://localhost:3000"] для CSR. DEBUG=true включает Swagger. Для production остановить dev, при работающем API выполнить npm run build && npm start.

## Проверки
- curl http://127.0.0.1:8000/menu/items — массив блюд.
- curl -s http://localhost:3000/menu | grep Сырники — серверный HTML.
- /menu/ID — название, цена, title, description, og:title; ID взять из API.
- Несуществующий ID при работающем API — notFound; при остановленном API открыть ранее не кешированный ID для error.tsx и повторить после запуска.
- ISR: изменить цену через авторизованный PATCH /menu/items/ID; в production обновить страницу до и после 60 секунд. После истечения TTL первый запрос может получить старую версию и запустить фоновую регенерацию; обновить ещё раз. При отказе API ISR может сохранять последнюю успешную версию.
- /menu-csr: в исходном HTML нет карточек блюд, браузер запрашивает API после JS.
- npm run typecheck — проверка TypeScript.

## Сравнение
| Метрика | SSR/ISR /menu | CSR /menu-csr |
|---|---|---|
| Блюда в исходном HTML (ожидается) | Да | Нет |
| Запрос API из браузера | Нет | Да |
| Первый контент меню | Серверный HTML | После JS и fetch |
| FCP, мс, замер 1 | не измерено | не измерено |
| FCP, мс, замер 2 | не измерено | не измерено |
| FCP, мс, замер 3 | не измерено | не измерено |

Для замеров: Chrome DevTools → Network → Disable cache, Performance → запись перезагрузки → FCP. Сделать по три замера в одинаковых условиях production, записать также время появления первой карточки (FCP может учитывать шапку или skeleton). Сравнить медианы. Фактические замеры не выполнены, числа не выдуманы. SSR/ISR позволяет поисковику получить готовые данные и обычно сокращает ожидание карточек; CSR удобен для интерактивных кабинетов. ISR уменьшает повторные запросы к API ценой возможной задержки обновления. Реальное преимущество по времени зависит от сети, кеша и сервера.

## Контрольные вопросы
1. Server Component выполняется на сервере (menu/page.tsx); Client Component использует браузерные хуки (menu-csr/page.tsx).
2. SSR отдаёт данные в HTML, что полезно публичной витрине и SEO.
3. Просмотреть исходный HTML или curl, а не только DOM в Elements.
4. loading показывает ожидание, error перехватывает ошибки сегмента и позволяет повторить запрос.
5. В Next.js 16 params асинхронны: await params извлекает id.
6. Redis кеширует данные API, Next.js — fetch и результаты рендеринга.
7. Open Graph задаёт превью ссылки в мессенджерах и соцсетях.
8. BFF — адаптированный под клиент слой API; GraphQL не выбран в этой работе.

Сборка и браузерные замеры требуют локального запуска; статус проверок не подтверждён.
