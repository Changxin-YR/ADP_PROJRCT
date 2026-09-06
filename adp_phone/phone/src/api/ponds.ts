import apiClient from './client';
import { ApiResponse, PaginatedData, Pond } from '../types';

const BASE = '/api/v1/master-data/ponds';

export const pondsApi = {
  async list(page = 1, pageSize = 20, search?: string): Promise<PaginatedData<Pond>> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (search) params.search = search;
    const res = await apiClient.get<ApiResponse<PaginatedData<Pond>>>(BASE, { params });
    return res.data;
  },

  async getById(id: number): Promise<Pond> {
    const res = await apiClient.get<ApiResponse<{ record: Pond }>>(`${BASE}/${id}`);
    return res.data.record;
  },

  async create(data: Record<string, unknown>): Promise<Pond> {
    const res = await apiClient.post<ApiResponse<Pond>>(BASE, data);
    return res.data;
  },

  async update(id: number, data: Record<string, unknown>): Promise<Pond> {
    const res = await apiClient.patch<ApiResponse<{ record: Pond }>>(`${BASE}/${id}`, data);
    return res.data.record;
  },

  async submit(id: number, expectedVersion: number): Promise<Pond> {
    const res = await apiClient.post<ApiResponse<{ record: Pond }>>(
      `${BASE}/${id}/submit`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  async verify(id: number, expectedVersion: number): Promise<Pond> {
    const res = await apiClient.post<ApiResponse<{ record: Pond }>>(
      `${BASE}/${id}/verify`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  async delete(id: number): Promise<void> {
    await apiClient.delete(`${BASE}/${id}`);
  },
};

export default pondsApi;
