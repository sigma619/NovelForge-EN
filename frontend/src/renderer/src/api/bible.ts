import request from './request'
import type { components } from '@renderer/types/generated'

// Backend-generated types (single source of truth)
export type BibleDashboardResponse = components['schemas']['BibleDashboardResponse']
export type BibleAuditResponse = components['schemas']['BibleAuditResponse']
export type RelationshipMatrixResponse = components['schemas']['RelationshipMatrixResponse']
export type KnowledgeMatrixResponse = components['schemas']['KnowledgeMatrixResponse']
export type CompileContextRequest = components['schemas']['CompileContextRequest']
export type CompileContextResponse = components['schemas']['CompileContextResponse']
export type CompiledBlockRead = components['schemas']['CompiledBlockRead']
export type BibleUpdateExtractRequest = components['schemas']['BibleUpdateExtractRequest']
export type BibleUpdateReviewRead = components['schemas']['BibleUpdateReviewRead']
export type BibleUpdateReviewListResponse = components['schemas']['BibleUpdateReviewListResponse']
export type BibleUpdateDecideRequest = components['schemas']['BibleUpdateDecideRequest']
export type BibleUpdateApplyResult = components['schemas']['BibleUpdateApplyResult']
export type ChangeDecision = components['schemas']['ChangeDecision']
export type ProposedChange = components['schemas']['ProposedChange']
export type BibleUpdateProposal = components['schemas']['BibleUpdateProposal']
export type DecisionAction = ChangeDecision['action']
export type CharacterDeepenRequest = components['schemas']['CharacterDeepenRequest']
export type CardRead = components['schemas']['CardRead']

const opts = { showLoading: false }

export function getBibleDashboard(projectId: number): Promise<BibleDashboardResponse> {
  return request.get('/bible/dashboard', { project_id: projectId }, '/api', opts)
}

export function getBibleAudit(projectId: number, currentChapter?: number): Promise<BibleAuditResponse> {
  return request.get('/bible/audit', { project_id: projectId, current_chapter: currentChapter }, '/api', opts)
}

export function getRelationshipMatrix(projectId: number): Promise<RelationshipMatrixResponse> {
  return request.get('/bible/relationships', { project_id: projectId }, '/api', opts)
}

export function getKnowledgeMatrix(projectId: number): Promise<KnowledgeMatrixResponse> {
  return request.get('/bible/knowledge-matrix', { project_id: projectId }, '/api', opts)
}

export function compileBibleContext(body: CompileContextRequest): Promise<CompileContextResponse> {
  return request.post('/bible/compile-context', body, '/api', opts)
}

export function deepenCharacter(body: CharacterDeepenRequest): Promise<CardRead> {
  return (request as any).request({
    method: 'POST',
    url: '/api/bible/characters/deepen',
    data: body,
    showLoading: false,
    timeout: Math.max(300_000, ((body.timeout || 0) * 1000) + 30_000),
  })
}

export function extractBibleUpdates(body: BibleUpdateExtractRequest): Promise<BibleUpdateReviewRead> {
  return (request as any).request({
    method: 'POST',
    url: '/api/bible/updates/extract',
    data: body,
    showLoading: false,
    timeout: Math.max(300_000, ((body.timeout || 0) * 1000) + 30_000),
  })
}

export function listBibleUpdates(projectId: number, status?: string): Promise<BibleUpdateReviewListResponse> {
  return request.get('/bible/updates', { project_id: projectId, status }, '/api', opts)
}

export function getBibleUpdate(reviewId: number): Promise<BibleUpdateReviewRead> {
  return request.get(`/bible/updates/${reviewId}`, undefined, '/api', opts)
}

export function decideBibleUpdate(reviewId: number, body: BibleUpdateDecideRequest): Promise<BibleUpdateApplyResult> {
  return request.post(`/bible/updates/${reviewId}/decide`, body, '/api', opts)
}

export function deleteBibleUpdate(reviewId: number): Promise<{ success: boolean }> {
  return request.delete(`/bible/updates/${reviewId}`, undefined, '/api', opts)
}
