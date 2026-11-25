export type MenuItem={id:number;name:string;price:number|string;category_name?:string;category_id?:number};
export const formatPrice=(price:MenuItem['price'])=>new Intl.NumberFormat('ru-RU',{style:'currency',currency:'RUB'}).format(Number(price));
const base=()=> (process.env.API_URL || 'http://127.0.0.1:8000').replace(/\/$/,'');
async function request(path:string){const response=await fetch(base()+path,{next:{revalidate:60},signal:AbortSignal.timeout(8000)});return response;}
export async function getMenuItems():Promise<MenuItem[]>{const r=await request('/menu/items');if(!r.ok)throw new Error('API: '+r.status);const data=await r.json();if(!Array.isArray(data))throw new Error('Неверный формат меню');return data;}
export async function getMenuItem(id:string):Promise<MenuItem|null>{if(!/^\d+$/.test(id))return null;const r=await request('/menu/items/'+encodeURIComponent(id));if(r.status===404)return null;if(!r.ok)throw new Error('API: '+r.status);return r.json();}
