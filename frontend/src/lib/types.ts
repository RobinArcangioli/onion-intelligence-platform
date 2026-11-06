export interface Identity { username: string; role: "VIEWER"|"ANALYST"|"ADMIN"; legacy: boolean }
export interface Page<T> { total: number; limit: number; offset: number; items: T[] }
export interface Source {
  id: string; canonical_url: string; name: string; description: string; category: string;
  availability_status: string; approved_for_collection: boolean; collection_enabled: boolean;
  is_active: boolean; priority: number; created_at: string; updated_at: string;
  deleted_at: string | null;
}
export interface Observation {
  id: string; job_id: string; source_id: string; http_status: number; content_type: string;
  response_bytes: number; title: string; description: string; text_sha256: string;
  text_length: number; change_status: string; relevance_score: number;
  keyword_hits: number; discovered_links: number; created_at: string;
}
export interface Discovery {
  id: string; source_id: string; target_url: string; status: string;
  evidence_kind: string; reviewed_at: string | null;
  first_seen_at: string; last_seen_at: string;
}
export interface Job { id: string; source_id: string; status: string; error_code: string | null; created_at: string; started_at: string | null; finished_at: string | null }
export interface Classification { id: string; observation_id: string; source_id: string; category: string; confidence: number; evidence_codes: string[]; ruleset_version: string; review_status: string; reviewed_at: string | null; created_at: string }
export interface Indicator { id: string; observation_id: string; source_id: string; indicator_type: string; public_reference: string; verification_status: string; confidence: number; evidence_codes: string[]; review_status: string; analyst_priority: string; reviewed_at: string | null; created_at: string }
export interface IocCandidate { id:string; observation_id:string; source_id:string; indicator_type:'DOMAIN'|'IPV4'|'IPV6'|'SHA256'; normalized_value:string; confidence:number; evidence_codes:string[]; ruleset_version:string; review_status:string; analyst_priority:string; reviewed_at:string|null; created_at:string }
export interface IocCorrelation { indicator_type:string; normalized_value:string; mentions:number; source_count:number; observation_count:number; first_seen_at:string; last_seen_at:string }
export interface PublicReference { reference:string; mentions:number; source_count:number; observation_count:number; reviewed_mentions:number; first_seen_at:string; last_seen_at:string }
export interface PublicReferenceEvidence { indicator_id:string; observation_id:string; source_id:string; observed_at:string; review_status:string; analyst_priority:string; confidence:number; evidence_codes:string[]; ruleset_version:string }
export interface Correlation { indicator_id: string; observation_id: string; source_id: string; watchlist_id: string; occurrences: number; relevance_score: number }
export interface Alert { id: string; source_id: string; observation_id: string; event_type: string; signal_code: string; priority: string; verification_status: string; relevance_score: number; status: string; created_at: string; acknowledged_at: string | null; resolved_at: string | null }
export interface Report { title?: string | null; company_name?: string | null; id: string; source_id: string | null; period_start: string; period_end: string; created_at: string }
export interface Watchlist { id: string; name: string; is_active: boolean; created_at: string }
export interface Rule { id: string; watchlist_id: string; phrase: string; weight: number; is_active: boolean; created_at: string }
export interface Audit { id: string; actor: string; action: string; details: Record<string, unknown>; created_at: string }

// M5-C: derived documentary quality, never a threat or attribution score.
export interface MentionQuality {
  id:string;kind:'IOC'|'CVE';indicator_type:string;reference:string;observation_id:string;source_id:string;
  original_confidence:number;review_status:string;analyst_priority:string;observed_at:string;
  documentary_quality:number;freshness:'CURRENT'|'AGING'|'STALE';age_days:number;
  explanation_codes:string[];rubric_version:string;
}
export interface CveIocLink {cve:string;ioc_type:string;ioc_value:string;observation_count:number;source_count:number;first_seen_at:string;last_seen_at:string}
export interface CtiReviewEvent {audit_id:string;actor:string;at:string;decision:string;analyst_priority:string;reason_code:string|null}

// M6-A: human-led case tracking; no collected page excerpts.
export type CaseStatus = 'OPEN'|'IN_REVIEW'|'ESCALATED'|'CLOSED';
export type CaseAction = 'ASSIGN'|'UNASSIGN'|'START_REVIEW'|'ESCALATE'|'RETURN_REVIEW'|'CLOSE'|'SET_PRIORITY';
export interface AnalystCase {
  id:string;alert_id:string;status:CaseStatus;assignee_id:string|null;assignee_username:string|null;
  version:number;priority:CasePriority;closure_code:string|null;created_by:string;created_at:string;updated_at:string;closed_at:string|null;
}
export interface AnalystCaseEvent {
  id:string;case_id:string;version:number;actor:string;action:string;from_status:string|null;
  to_status:string;assignee_username:string|null;reason_code:string|null;created_at:string;
}

export type CasePriority = 'UNASSESSED'|'LOW'|'MEDIUM'|'HIGH'|'CRITICAL';
export type CaseNoteCode = 'ANALYST_CONTEXT'|'FOLLOW_UP'|'FALSE_POSITIVE_CHECK'|'ESCALATION_CONTEXT';
export interface CaseNote {id:string;case_id:string;case_version:number;actor:string;note_code:CaseNoteCode;body:string;created_at:string}
export interface CaseNotificationPreview {enabled:false;delivery:'DISABLED';requires_manual_review:true;template:string;case_id:string;status:CaseStatus;priority:CasePriority;version:number;contents:'METADATA_ONLY';destinations:[]}

// M6-C: reviewed LOCAL notification snapshots only; no delivery transport.
export interface CaseNotificationPolicy {
  id:string;code:string;target_status:CaseStatus;minimum_priority:CasePriority;
  approved:boolean;enabled:boolean;version:number;created_by:string;updated_by:string;
  created_at:string;updated_at:string;transport:'NONE';
}
export interface CaseNotificationDraft {
  id:string;policy_id:string;case_id:string;case_version:number;created_by:string;
  delivery_status:'NOT_SENT';created_at:string;destinations:[];
  payload:{template:string;case_id:string;status:CaseStatus;priority:CasePriority;
    version:number;policy_code:string;content:'METADATA_ONLY'};
}
export interface CaseOperationsSummary {
  report_type:'CASE_OPERATIONS_METADATA_V1';contents:'AGGREGATED_ONLY';
  total_cases:number;by_status:Record<CaseStatus,number>;
  by_priority:Record<CasePriority,number>;open_unassigned:number;
  notification_drafts:number;notifications_sent:0;external_transport:'NOT_IMPLEMENTED';
}
