#!/usr/bin/env python3
import json
import os
from pathlib import Path
import tempfile
os.environ.setdefault('MPLCONFIGDIR',str(Path(tempfile.gettempdir())/'rpm-lab05-mpl'))
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
ROOT=Path(__file__).resolve().parents[1]
D=ROOT/'docs/demo'
data=json.loads((D/'results.json').read_text())
a,b=(data['durations'][key] for key in ('sync','celery'))
fig,ax=plt.subplots(figsize=(8,4.5),layout='constrained')
colors=['#607d8b','#1976d2']
bars=ax.barh(['Синхронно','Celery'],[a['median_ms'],b['median_ms']],color=colors,height=.55)
ax.bar_label(bars,fmt='%.2f мс',padding=5)
for y,values in enumerate((a['samples_ms'],b['samples_ms'])):
    ax.scatter(values,[y]*len(values),color='black',marker='|',s=120,label='Отдельные запросы' if y==0 else None)
ax.set_xlabel('Время HTTP-ответа, мс');ax.set_title('POST /orders/create: 3 запроса на режим, медиана')
ax.set_xlim(0,max(a['samples_ms']+b['samples_ms'])*1.2)
ax.spines[['top','right']].set_visible(False);ax.legend(loc='lower right')
fig.savefig(ROOT/'docs/response-time.png',dpi=160);plt.close(fig)
block='## Измеренное время ответа\n\n![Ответ API до и после Celery](docs/response-time.png)\n\n| Режим | 3 HTTP-запроса, мс | Медиана, мс |\n|---|---|---:|\n'
for title,values in [('Синхронно',a),('Celery',b)]:
    block+=f"| {title} | {', '.join(f'{x:.2f}' for x in values['samples_ms'])} | {values['median_ms']:.2f} |\n"
block+=f"\nВ этом опыте ответ ускорился в **{a['median_ms']/b['median_ms']:.1f} раза**. Измерены реальные HTTP-запросы с JWT, PostgreSQL и Redis; воркер работает отдельным prefork-процессом. Тяжёлые операции — явно заданные учебные симуляции 2 + 1 + 1 с, а не внешние SMTP/SMS-провайдеры. Celery сокращает ожидание ответа, не общую длительность работы. Три измерения показывают этот сценарий, не являются оценкой p95 или SLA. Порядок — sync, затем celery; включена первая постановка с подключением к брокеру.\n"
text=block+'\n## Проверенные сценарии\n\n'
for key,value in data['checks'].items():text+=f'- `{key}`: `{value}`.\n'
text+='\nЧетыре попытки email заказа №5 фиксируются в task_logs. Первые три RETRYING, последняя DEAD; последняя Celery-задача FAILURE, в Redis лежит отдельное сообщение dlq. Обычный worker слушает только default. Остальные уведомления и сам заказ сохранены.\n\n'
text+='[Машиночитаемый результат](demo/results.json) · [Worker](demo/worker.log) · [Worker после перезапуска](demo/worker-restarted.log) · [Beat](demo/beat.log).\n\n'
text+='## Flower: реальные снимки\n\n![Список задач и статусов](demo/flower-tasks.png)\n\n![Неуспешная задача после ретраев](demo/flower-failed-task.png)\n'
(ROOT/'docs/measurements.md').write_text(text.replace('(docs/response-time.png)','(response-time.png)'))
p=ROOT/'README.md';s=p.read_text();start=s.index('<!-- measurements:start -->');end=s.index('<!-- measurements:end -->')+len('<!-- measurements:end -->')
p.write_text(s[:start]+'<!-- measurements:start -->\n'+block+'<!-- measurements:end -->'+s[end:])
assert data['eager'] is False and data['checks']['real_retries_attempts']==4
assert data['checks']['worker_child_killed_during_pdf'] is True
assert all(value for value in data['checks'].values())
print('PASS: measured graph, README and real-process checks')
