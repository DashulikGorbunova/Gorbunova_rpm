'use client';
import {useEffect,useState} from 'react';
import {DishCard} from '@/components/DishCard';
import type {MenuItem} from '@/lib/api';
export default function CSR(){const [items,setItems]=useState<MenuItem[]|null>(null);const [error,setError]=useState(false);const [attempt,setAttempt]=useState(0);
useEffect(()=>{const controller=new AbortController();setError(false);setItems(null);fetch((process.env.NEXT_PUBLIC_API_URL||'http://127.0.0.1:8000')+'/menu/items',{cache:'no-store',signal:controller.signal}).then(r=>{if(!r.ok)throw new Error('API');return r.json();}).then(data=>{if(!Array.isArray(data))throw new Error('JSON');if(!controller.signal.aborted)setItems(data);}).catch(()=>{if(!controller.signal.aborted)setError(true);});return ()=>controller.abort();},[attempt]);
return <main className="mx-auto max-w-5xl px-6 py-10"><h1 className="text-4xl font-bold">Меню — CSR</h1><p className="mt-2 text-stone-600">Данные загружаются в браузере после JavaScript.</p>{error?<div role="alert" className="mt-8">Не удалось загрузить меню. <button className="underline" onClick={()=>setAttempt(a=>a+1)}>Попробовать снова</button></div>:items===null?<p role="status" className="mt-8">Загрузка…</p>:items.length===0?<p className="mt-8">Меню пока пустое.</p>:<div className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{items.map(item=><DishCard key={item.id} item={item}/>)}</div>}</main>}
