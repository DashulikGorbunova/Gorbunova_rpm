import type { Metadata } from 'next';
import Link from 'next/link';
import './globals.css';
export const metadata: Metadata = { title: {default:'Сириус.Еда',template:'%s | Сириус.Еда'}, description:'Свежие блюда на каждый день' };
export default function Layout({children}:{children:React.ReactNode}) {
return <html lang="ru"><body><header className="border-b border-stone-200 bg-white"><nav className="mx-auto flex max-w-5xl flex-wrap items-center gap-6 px-6 py-5"><Link href="/" className="mr-auto text-xl font-bold text-green-800">Сириус.Еда</Link><Link href="/menu">Меню</Link><Link href="/menu-csr">CSR</Link></nav></header>{children}<footer className="mx-auto max-w-5xl px-6 py-10 text-sm text-stone-500">Сириус.Еда · Учебный проект</footer></body></html>;
}