import apiClient from './client';
import { ApiResponse, PaginatedData, Batch, DailyOperation } from '../types';

const BASE = '/api/v1/production';

export const productionApi = {
  // Batches
  async listBatches(page = 1, pageSize = 20, status?: string): Promise<PaginatedData<Batch>> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (status) params.status = status;
    const res = await apiClient.get<ApiResponse<PaginatedData<Batch>>>(BASE + '/batches', { params });
    return res.data;
  },

  async getBatch(id: number): Promise<Batch> {
    const res = await apiClient.get<ApiResponse<{ record: Batch }>>(`${BASE}/batches/${id}`);
    return res.data.record;
  },

  async createBatch(data: Record<string, unknown>): Promise<Batch> {
    const res = await apiClient.post<ApiResponse<{ record: Batch }>>(BASE + '/batches', data);
    return res.data.record;
  },

  async submitBatch(id: number, expectedVersion: number): Promise<Batch> {
    const res = await apiClient.post<ApiResponse<{ record: Batch }>>(
      `${BASE}/batches/${id}/submit`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  async verifyBatch(id: number, expectedVersion: number): Promise<Batch> {
    const res = await apiClient.post<ApiResponse<{ record: Batch }>>(
      `${BASE}/batches/${id}/verify`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  async reconcileBatch(id: number): Promise<any> {
    const res = await apiClient.get<ApiResponse<any>>(`${BASE}/batches/${id}/reconciliation`);
    return res.data;
  },

  // Samplings
  async listSamplings(page = 1, pageSize = 20): Promise<PaginatedData<any>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<any>>>(
      BASE + '/samplings',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },

  async createSampling(data: Record<string, unknown>): Promise<any> {
    const res = await apiClient.post<ApiResponse<{ record: any }>>(BASE + '/samplings', data);
    return res.data.record;
  },

  // Transfers
  async listTransfers(page = 1, pageSize = 20): Promise<PaginatedData<any>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<any>>>(
      BASE + '/transfers',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },

  // Losses
  async listLosses(page = 1, pageSize = 20): Promise<PaginatedData<any>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<any>>>(
      BASE + '/losses',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },

  // Harvests
  async listHarvests(page = 1, pageSize = 20): Promise<PaginatedData<any>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<any>>>(
      BASE + '/harvests',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },

  // Daily Operations
  async listDailyOps(page = 1, pageSize = 20): Promise<PaginatedData<DailyOperation>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<DailyOperation>>>(
      BASE + '/daily-operations',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },

  async createDailyOps(data: Record<string, unknown>): Promise<DailyOperation> {
    const res = await apiClient.post<ApiResponse<{ record: DailyOperation }>>(
      BASE + '/daily-operations', data
    );
    return res.data.record;
  },
};

export default productionApi;
