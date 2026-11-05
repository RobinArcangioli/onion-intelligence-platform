/** Public reads never receive or forward an operator token. */
import { safePath } from './api.ts';

export type PublicActivity = {date:string;source_name:string;status:'COMPLETED'|'FAILED';response_bytes:number|null;text_characters:number|null};
export type PublicTotals = {observations:number;discoveries:number;classifications:number;indicators:number;alerts:number};
export type PublicReportContent = {schema_version:'PUBLIC_TOTALS_V1';period_start:string;period_end:string;totals:PublicTotals;disclaimer:string};
export type PublishedReport = {id:string;published_at:string;content:PublicReportContent};
export type PublicationPreview = {content:PublicReportContent;digest:string;publication_id:string|null};
export const totalLabels: Record<keyof PublicTotals,string> = {observations:'Observations',discoveries:'Découvertes',classifications:'Classifications',indicators:'Mentions CTI',alerts:'Alertes documentaires'};

export async function publicGet<T>(path:string, signal?:AbortSignal):Promise<T> {
  const url=safePath(path);
  if (!/^\/api\/public\/v1\/(activity|reports(?:\/[0-9a-f-]{36})?)(\?[^#]*)?$/.test(url)) {
    throw new Error('Invalid public route');
  }
  const response=await fetch(url,{method:'GET',credentials:'omit',cache:'no-store',redirect:'error',signal});
  // Do not reflect server error bodies in the anonymous interface.
  if(!response.ok) throw new Error(response.status===404?'Ce rapport n’est plus public.':'La vitrine est temporairement indisponible.');
  return response.json() as Promise<T>;
}
