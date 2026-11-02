#!/usr/bin/env python3
"""Render plots and measured comparison from Locust + PostgreSQL artifacts."""
import json
import os
import tempfile
from pathlib import Path
os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'rpm-lab04-mpl'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/load'
data=json.loads((OUT/'summary.json').read_text())
phases=[data['phases'][p] for p in ('baseline','cached')]
labels=['Без кеша','Cache-Aside']
colors=['#607d8b','#1976d2']
fig,axes=plt.subplots(2,2,figsize=(11,7),layout='constrained')
for ax,values,title,unit in [
    (axes[0,0],[p['steady']['steady_rps'] for p in phases],'RPS при 500 пользователях','запросов/с'),
    (axes[0,1],[p['steady']['steady_p95_ms'] for p in phases],'p95 при 500 пользователях','мс'),
    (axes[1,0],[p['postgres']['menu_select_calls']/p['requests']*1000 for p in phases],'SELECT меню на 1000 HTTP-запросов','SELECT'),
    (axes[1,1],[p['host_load_average_1m_mean'] for p in phases],'Load Average 1 min: общий хост','среднее за прогон')]:
    bars=ax.bar(labels,values,color=colors,width=.55)
    ax.bar_label(bars,fmt='%.2f',padding=3)
    ax.set_title(title);ax.set_ylabel(unit);ax.set_ylim(0,max(values)*1.25 if max(values)>0 else 1)
    ax.spines[['top','right']].set_visible(False)
fig.suptitle('Locust: 500 пользователей, spawn 10/с, ramp-up 50 с + plateau ~35 с')
fig.savefig(ROOT/'docs/comparison.png',dpi=160)
plt.close(fig)
before,after=phases
r='''# Измерения Cache-Aside

Измерено 2 ноября 2026 г. Настройки и сырые значения: [summary.json](load/summary.json).

![Сравнение RPS, p95, SELECT и Load Average](comparison.png)

Один Uvicorn worker, настоящая JWT-аутентификация студента, 500 пользователей Locust, spawn rate 10/с, ожидание между запросами 0.1–0.5 с. Каждый прогон длится 85 с: ~50 с разгона и ~35 с при 500 пользователях. В тестовой базе 10000 синтетических блюд, 3 категории; API возвращает первые 100 с JOIN и сортировкой. В baseline выключен только кеш (`CACHE_ENABLED=false`); SQL, авторизация, данные и настройки сервера одинаковы. Прогоны последовательные, без искусственного sleep в запросе или отключения безопасности. Устойчивое окно — строго от 50-й до 85-й секунды, без завершающего drain; число ответов и итоговые метрики берутся из events.quitting Locust, а не последнего периодического CSV-снимка. Это одна пара прогонов на общем облачном хосте; выводы не являются SLA или универсальным коэффициентом ускорения.

## Всё окно (разгон + плато + завершение запросов)

| Метрика | До | После |
|---|---:|---:|
'''
for title,key,fmt in [('HTTP-запросов','requests','.0f'),('Ошибок','failures','.0f'),('RPS','rps','.2f'),('Средняя latency, мс','mean_ms','.2f'),('p95, мс (бакет Locust)','p95_ms','.2f'),('Load Average 1 min, среднее хоста','host_load_average_1m_mean','.2f')]:
    r+=f'| {title} | {before[key]:{fmt}} | {after[key]:{fmt}} |\n'
r+='\n## Плато после 50-й секунды\n\n| Метрика | До | После |\n|---|---:|---:|\n'
for title,key,fmt in [('RPS','steady_rps','.2f'),('Средняя latency, мс','steady_mean_ms','.2f'),('p95, мс (по отдельным ответам)','steady_p95_ms','.2f'),('Запросов в окне','steady_requests','.0f')]:
    r+=f'| {title} | {before["steady"][key]:{fmt}} | {after["steady"][key]:{fmt}} |\n'
r+='\n## Работа PostgreSQL\n\n| Метрика | До | После |\n|---|---:|---:|\n'
for title,key,fmt in [('SELECT меню','menu_select_calls','.0f'),('Время исполнения SELECT меню, мс','menu_exec_ms','.2f'),('Строк от SELECT меню','menu_rows','.0f'),('Все SELECT (auth, pre-ping, снимки)','select_calls','.0f')]:
    r+=f'| {title} | {before["postgres"][key]:{fmt}} | {after["postgres"][key]:{fmt}} |\n'
r+=f"| SELECT меню на HTTP-запрос | {before['postgres']['menu_select_calls']/before['requests']:.4f} | {after['postgres']['menu_select_calls']/after['requests']:.4f} |\n"
r+=f"| Все SELECT на HTTP-запрос | {before['postgres']['select_calls']/before['requests']:.4f} | {after['postgres']['select_calls']/after['requests']:.4f} |\n"
r+='''
Счётчики — разность снимков pg_stat_statements в выделенной базе до и после Locust. Запросы меню выделены по `FROM menu`, учитывается реальное число исполнений в PostgreSQL. Прогрев происходит до первого снимка, поэтому его один SELECT не включён в окно кешированного прогона. Ошибок HTTP нет. Все SELECT не исчезают: каждый защищённый запрос продолжает проверять сессию и пользователя в БД, а пул делает pre-ping. Редкие SELECT меню после прогрева — fallback при коротком таймауте Redis на загруженном хосте; они включены в счётчик и не скрываются. Поэтому кеш снимает повторное чтение **меню**, а не всю нагрузку с PostgreSQL. Метрика Load Average снята через os.getloadavg с общего хоста, включает генератор нагрузки и другие процессы, не является CPU PostgreSQL; по ней нельзя приписать эффект только СУБД.

'''
r+=f'На плато RPS изменился в {after["steady"]["steady_rps"]/before["steady"]["steady_rps"]:.2f} раза; p95 — с {before["steady"]["steady_p95_ms"]:.2f} до {after["steady"]["steady_p95_ms"]:.2f} мс. '
r+='Это фактический результат данной модели; обещание «ускорения в десятки раз» из примера задания не используется как измеренный факт. Узким местом могут оставаться аутентификация, сериализация, пул соединений, один worker и CPU хоста. Для production нужны повторные прогоны и распределённый генератор.\n\n'
r+='### Отдельная первая попытка: исчерпание пула\n\nДо исправления времени жизни соединений первый baseline получил 678 ответов, из них 66 HTTP 500; p95 Locust — 65000 мс. Соединения удерживались до финализации HTTP-ответа, что при 500 пользователях приводило к таймауту QueuePool (5 + 10). Артефакты сохранены [отдельно](load/initial-pool-exhaustion/baseline_stats.csv). Эти цифры не включены в график основной пары. Перед повторением **обоих** прогонов освобождены read-соединения аутентификации до возврата dependency и введён ограниченный контекст чтения меню, закрывающий соединение до сериализации. Добавлен регрессионный тест. Поэтому улучшение после этой починки не приписывается Redis.\n\n'
r+='[Baseline CSV](load/baseline_stats.csv) · [Cached CSV](load/cached_stats.csv) · [История baseline](load/baseline_stats_history.csv) · [История cached](load/cached_stats_history.csv). Сводки steady-window содержат число реально запущенных пользователей, финальные метрики и ошибки. Периодические CSV могут не включать последние ответы при завершении; итоговая таблица использует финальный JSON. Небольшой избыток SQL над завершёнными HTTP-запросами возможен из-за запросов, начатых при остановке пользователей. Bearer-токен, пароль и URL с паролем в артефакты не записываются.\n'
(ROOT/'docs/measurements.md').write_text(r)
block='## Измеренный результат\n\n![Сравнение RPS, p95, SELECT и Load Average](docs/comparison.png)\n\n| Метрика | До | После |\n|---|---:|---:|\n'
for title,key in [('RPS при 500 пользователях','steady_rps'),('p95 при 500 пользователях, мс','steady_p95_ms')]:
    block+=f"| {title} | {before['steady'][key]:.2f} | {after['steady'][key]:.2f} |\n"
block+=f"| SELECT меню за прогон | {before['postgres']['menu_select_calls']} | {after['postgres']['menu_select_calls']} |\n"
block+=f"| Load Average 1 min общего хоста, среднее | {before['host_load_average_1m_mean']:.2f} | {after['host_load_average_1m_mean']:.2f} |\n"
block+='\nВ обоих режимах достигнуты 500 пользователей, HTTP-ошибок нет. RPS/p95 относятся к окну 50–85 с; SELECT и Load Average — ко всему прогону. Авторизация сохранена. [Методика, ограничения и исходные данные](docs/measurements.md).\n'
readme=ROOT/'README.md'
content=readme.read_text()
start=content.index('<!-- measurements:start -->')
end=content.index('<!-- measurements:end -->')+len('<!-- measurements:end -->')
readme.write_text(content[:start]+'<!-- measurements:start -->\n'+block+'<!-- measurements:end -->'+content[end:])
assert all(p['failures']==0 and p['steady']['peak_spawned_users']==500 for p in phases)
assert before['postgres']['menu_select_calls']>=before['requests']*.99
assert after['postgres']['menu_select_calls']<max(1,after['requests']*.01)
print('PASS: two 500-user runs; menu SQL reduced by >99%; report and chart generated')
