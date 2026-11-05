import { useEffect, useState } from 'react';
import { publicGet } from './publicApi';

/** Revalidate visible public data on navigation, focus and while it is displayed. */
export function usePublicResource<T>(path:string,refresh:number,active=true){
  const [data,setData]=useState<T|null>(null);
  const [loading,setLoading]=useState(true);const [error,setError]=useState('');
  useEffect(()=>{
    if(!active)return;
    let alive=true;let current:AbortController|undefined;
    async function load(initial=false){
      current?.abort();const abort=new AbortController();current=abort;
      if(initial){setLoading(true);setData(null);setError('');}
      try{
        const value=await publicGet<T>(path,abort.signal);
        if(alive&&!abort.signal.aborted){setData(value);setError('');}
      }catch(e){
        if(alive&&!abort.signal.aborted){setData(null);setError(e instanceof Error?e.message:'La vitrine est temporairement indisponible.');}
      }finally{if(alive&&!abort.signal.aborted)setLoading(false);}
    }
    const revalidate=()=>{if(document.visibilityState==='visible')void load();};
    void load(true);
    const timer=window.setInterval(revalidate,5000);
    window.addEventListener('focus',revalidate);
    document.addEventListener('visibilitychange',revalidate);
    return ()=>{alive=false;current?.abort();window.clearInterval(timer);window.removeEventListener('focus',revalidate);document.removeEventListener('visibilitychange',revalidate);};
  },[path,refresh,active]);
  return {data,loading,error};
}
