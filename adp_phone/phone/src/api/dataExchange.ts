import apiClient from './client';
import { ApiResponse, DataTemplate } from '../types';

const BASE = '/api/v1/data-exchange';

export interface MobileUploadFile {
  uri: string;
  name: string;
  type: string;
}

export interface ExportRequest {
  organization_id: number;
  resource: string;
  format: 'xlsx' | 'pdf';
  filters?: Record<string, unknown>;
}

type LegacyExportParams = Partial<Pick<ExportRequest, 'organization_id' | 'format' | 'filters'>>;

export const dataExchangeApi = {
  async listTemplates(): Promise<DataTemplate[]> {
    const res = await apiClient.get<ApiResponse<{ items: DataTemplate[] }>>(BASE + '/templates');
    return res.data.items;
  },

  async downloadTemplate(templateCode: string): Promise<any> {
    const res = await apiClient.get<any>(
      `${BASE}/templates/${templateCode}/download`,
      { responseType: 'blob' as any }
    );
    return res;
  },

  async previewImport(organizationId: number, templateCode: string, file: MobileUploadFile): Promise<any> {
    if (!Number.isInteger(organizationId) || organizationId < 1) {
      throw new Error('organization_id is required');
    }
    const fileData = new FormData();
    fileData.append('organization_id', String(organizationId));
    fileData.append('template_code', templateCode);
    fileData.append('file', file as any);
    const res = await apiClient.post<ApiResponse<any>>(
      `${BASE}/imports/preview`,
      fileData,
      { headers: { 'Content-Type': 'multipart/form-data' } }
    );
    return res.data;
  },

  async confirmImport(batchId: number): Promise<any> {
    const res = await apiClient.post<ApiResponse<any>>(
      `${BASE}/imports/${batchId}/confirm`,
      {}
    );
    return res.data;
  },

  async exportData(requestOrResource: ExportRequest | string, params: LegacyExportParams = {}): Promise<any> {
    const request: ExportRequest = typeof requestOrResource === 'string'
      ? {
          organization_id: params.organization_id as number,
          resource: requestOrResource,
          format: params.format || 'xlsx',
          filters: params.filters || {},
        }
      : { ...requestOrResource, filters: requestOrResource.filters || {} };
    if (!Number.isInteger(request.organization_id) || request.organization_id < 1) {
      throw new Error('organization_id is required');
    }
    const res = await apiClient.post<any>(
      `${BASE}/exports`,
      request,
      { responseType: 'blob' as any }
    );
    return res;
  },
};

export default dataExchangeApi;
