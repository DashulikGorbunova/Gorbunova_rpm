import type {Metadata} from 'next';
import Link from 'next/link';
import {notFound} from 'next/navigation';
import {getMenuItem,formatPrice} from '@/lib/api';
type Props={params:Promise<{id:string}>};
export const revalidate=60;
export async function generateStaticParams(){return [];}
export async function generateMetadata({params}:Props):Promise<Metadata>{const item=await getMenuItem((await params).id);if(!item)return {title:'Блюдо не найдено'};const description=item.name+' — '+formatPrice(item.price)+' в меню Сириус.Еды';return {title:item.name,description,openGraph:{title:item.name,description,type:'website'}};}
export default async function Dish({params}:Props){const item=await getMenuItem((await params).id);if(!item)notFound();return <main className="mx-auto max-w-3xl px-6 py-12"><Link href="/menu" className="text-green-800">← Назад к меню</Link><article className="mt-6 rounded-3xl border border-stone-200 bg-white p-8"><p className="text-green-700">{item.category_name}</p><h1 className="mt-3 text-4xl font-bold">{item.name}</h1><p className="mt-5 text-3xl font-bold text-green-800">{formatPrice(item.price)}</p></article></main>}
