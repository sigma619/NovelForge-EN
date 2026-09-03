import request from './request'
import type { components } from '@renderer/types/generated'

export type ManuscriptPreviewRequest = components['schemas']['ManuscriptPreviewRequest']
export type ManuscriptPreviewResponse = components['schemas']['ManuscriptPreviewResponse']
export type ManuscriptImportRequest = components['schemas']['ManuscriptImportRequest']
export type ManuscriptImportResponse = components['schemas']['ManuscriptImportResponse']
export type ManuscriptListResponse = components['schemas']['ManuscriptListResponse']
export type ChapterPreview = components['schemas']['ChapterPreview']

const opts = { showLoading: false }

export function previewManuscript(body: ManuscriptPreviewRequest): Promise<ManuscriptPreviewResponse> {
  return (request as any).request({ method: 'POST', url: '/api/lab/manuscript/preview', data: body, showLoading: false, timeout: 180_000 })
}

export function importManuscript(body: ManuscriptImportRequest): Promise<ManuscriptImportResponse> {
  return (request as any).request({ method: 'POST', url: '/api/lab/manuscript/import', data: body, showLoading: false, timeout: 300_000 })
}

export function listManuscript(projectId: number): Promise<ManuscriptListResponse> {
  return request.get('/lab/manuscript', { project_id: projectId }, '/api', opts)
}

export function getManuscriptDefaults(): Promise<{ volume_pattern: string; pattern_candidates: Array<{ name: string; pattern: string }>; supported_extensions: string[] }> {
  return request.get('/lab/manuscript/defaults', undefined, '/api', opts)
}

export function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => {
      const result = String(reader.result || '')
      const idx = result.indexOf(',')
      resolve(idx >= 0 ? result.slice(idx + 1) : result)
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(file)
  })
}
