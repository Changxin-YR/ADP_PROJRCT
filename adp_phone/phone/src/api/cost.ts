import apiClient from './client';
import { ApiResponse, PaginatedData, CostEntry, COST_CATEGORIES } from '../types';

const BASE = '/api/v1/cost';

export const costApi = {
  async getStructure(periodStart: string, periodEnd: string): Promise<any> {
    const res = await apiClient.get<ApiResponse<any>>(
      BASE + '/structure',
      { params: { period_start: periodStart, period_end: periodEnd } }
    );
    return res.data;
  },

  async listEntries(
    categoryCode: string,
    periodStart: string,
    periodEnd: string,
    page = 1,
    pageSize = 20
  ): Promise<PaginatedData<CostEntry>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<CostEntry>>>(
      BASE + '/entries',
      {
        params: {
          category_code: categoryCode,
          period_start: periodStart,
          period_end: periodEnd,
          page,
          page_size: pageSize,
        },
      }
    );
    return res.data;
  },

  async createEntry(data: Record<string, unknown>): Promise<CostEntry> {
    const res = await apiClient.post<ApiResponse<{ entry: CostEntry }>>(BASE + '/entries', data);
    return res.data.entry;
  },

  async submitEntry(id: number, data: Record<string, unknown>): Promise<CostEntry> {
    const res = await apiClient.post<ApiResponse<{ entry: CostEntry }>>(
      `${BASE}/entries/${id}/submit`, data
    );
    return res.data.entry;
  },

  async verifyEntry(id: number, data: Record<string, unknown>): Promise<CostEntry> {
    const res = await apiClient.post<ApiResponse<{ entry: CostEntry }>>(
      `${BASE}/entries/${id}/verify`, data
    );
    return res.data.entry;
  },

  async confirmEntry(id: number, data: Record<string, unknown>): Promise<CostEntry> {
    const res = await apiClient.post<ApiResponse<{ entry: CostEntry }>>(
      `${BASE}/entries/${id}/confirm`, data
    );
    return res.data.entry;
  },

  async getAllocationRules(mode = 'effective'): Promise<any> {
    const res = await apiClient.get<ApiResponse<any>>(
      BASE + '/allocation-rules',
      { params: { mode } }
    );
    return res.data;
  },

  async listExpenses(page = 1, pageSize = 20): Promise<PaginatedData<any>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<any>>>(
      BASE + '/expenses',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },

  async listSettlements(page = 1, pageSize = 20): Promise<PaginatedData<any>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<any>>>(
      BASE + '/settlements',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },
};

export default costApi;
