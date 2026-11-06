/** Public reads never receive or forward an operator token. */
import { safePath } from './api.ts';

export type PublicActivity = {date:string;source_name:string;status:'COMPLETED'|'FAILED';response_bytes:number|null;text_characters:number|null};
export type PublicTotals = {observations:number;discoveries:number;classifications:number;indicators:number;alerts:number};
export type DataCategory = 'CUSTOMER_RECORDS'|'CONTACT_DETAILS'|'EMPLOYEE_RECORDS'|'INTERNAL_DOCUMENTS'|'FINANCIAL_RECORDS';
export type PublicIncidentDraft = {title:string;company_name:string;sector:string;summary:string;data_categories:DataCategory[];affected_records:number|null;detected_at:string;recommendations:string;assessment:'SUSPECTED_DATA_LEAK';simulation:boolean};
export const dataLabels:Record<DataCategory,string>={CUSTOMER_RECORDS:'Dossiers clients',CONTACT_DETAILS:'Coordonnées',EMPLOYEE_RECORDS:'Dossiers collaborateurs',INTERNAL_DOCUMENTS:'Documents internes',FINANCIAL_RECORDS:'Données financières'};
export type PublicReportContent = {schema_version:'PUBLIC_TOTALS_V1'|'PUBLIC_REVIEW_V2';period_start:string;period_end:string;totals:PublicTotals;disclaimer:string;incident?:PublicIncidentDraft;publication_review?:'ADMIN_REVIEWED_FOR_PUBLICATION'};
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
