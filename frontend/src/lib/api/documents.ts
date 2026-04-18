import { apiClient } from './client';

export interface Document {
  id: string;
  integration_id: string;
  tenant_id: string;
  file_name: string;
  document_title?: string;
  source_type?: string;
  status: 'pending' | 'parsing' | 'chunking' | 'embedding' | 'completed' | 'failed';
  chunk_count?: number;
  created_at: string;
}

export interface UploadResponse {
  job_id: string;
  status: string;
  message: string;
  integration_id: string;
}

export interface JobStatus {
  job_id: string;
  status: 'pending' | 'parsing' | 'chunking' | 'embedding' | 'completed' | 'failed';
  file_name: string;
  total_chunks: number;
  processed_chunks: number;
  error_message?: string;
  created_at: string;
  updated_at: string;
  message: string;
}

interface ListDocumentsResponse {
  documents: Document[];
  message: string;
}

export async function listDocuments(integrationId: string): Promise<Document[]> {
  const res = await apiClient
    .get(`v1/integrations/${integrationId}/documents`)
    .json<ListDocumentsResponse>();
  return res.documents ?? [];
}

export async function uploadDocument(
  integrationId: string,
  file: File,
  documentTitle?: string
): Promise<UploadResponse> {
  const formData = new FormData();
  formData.append('file', file);
  if (documentTitle) {
    formData.append('document_title', documentTitle);
  }
  return apiClient
    .post(`v1/integrations/${integrationId}/documents`, { body: formData })
    .json<UploadResponse>();
}

export async function deleteDocument(documentId: string): Promise<void> {
  await apiClient.delete(`v1/documents/${documentId}`);
}

export async function getJobStatus(jobId: string): Promise<JobStatus> {
  return apiClient.get(`status/${jobId}`).json<JobStatus>();
}
