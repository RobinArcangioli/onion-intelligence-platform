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
export interface Indicator { id: string; observation_id: string; source_id: string; indicator_type: string; public_reference: string; verification_status: string; confidence: number; evidence_codes: string[]; created_at: string }
export interface Correlation { indicator_id: string; observation_id: string; source_id: string; watchlist_id: string; occurrences: number; relevance_score: number }
export interface Alert { id: string; source_id: string; observation_id: string; event_type: string; signal_code: string; priority: string; verification_status: string; relevance_score: number; status: string; created_at: string; acknowledged_at: string | null; resolved_at: string | null }
export interface Report { id: string; source_id: string | null; period_start: string; period_end: string; created_at: string }
export interface Watchlist { id: string; name: string; is_active: boolean; created_at: string }
export interface Rule { id: string; watchlist_id: string; phrase: string; weight: number; is_active: boolean; created_at: string }
export interface Audit { id: string; actor: string; action: string; details: Record<string, unknown>; created_at: string }
