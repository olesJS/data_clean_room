import { endpoints } from '../config'
import { request } from './client'
import type { AuditLogEntry, CatalogItem } from './types'

export function fetchCatalog(): Promise<CatalogItem[]> {
  return request<CatalogItem[]>(endpoints.catalog)
}

export function fetchAuditLog(): Promise<AuditLogEntry[]> {
  return request<AuditLogEntry[]>(endpoints.audit)
}
