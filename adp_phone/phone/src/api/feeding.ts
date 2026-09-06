import apiClient from './client';
import { ApiResponse, PaginatedData, FeedPlan, FeedTask, FeedLog } from '../types';

const BASE = '/api/v1/production';

export const feedingApi = {
  // Feed Plans
  async listPlans(page = 1, pageSize = 20, status?: string): Promise<PaginatedData<FeedPlan>> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (status) params.status = status;
    const res = await apiClient.get<ApiResponse<PaginatedData<FeedPlan>>>(BASE + '/feed-plans', { params });
    return res.data;
  },

  async createPlan(data: Record<string, unknown>): Promise<FeedPlan> {
    const res = await apiClient.post<ApiResponse<{ record: FeedPlan }>>(BASE + '/feed-plans', data);
    return res.data.record;
  },

  async submitPlan(id: number, expectedVersion: number): Promise<FeedPlan> {
    const res = await apiClient.post<ApiResponse<{ record: FeedPlan }>>(
      `${BASE}/feed-plans/${id}/submit`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  // Feed Tasks
  async listTasks(page = 1, pageSize = 20, status?: string): Promise<PaginatedData<FeedTask>> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (status) params.status = status;
    const res = await apiClient.get<ApiResponse<PaginatedData<FeedTask>>>(BASE + '/feed-tasks', { params });
    return res.data;
  },

  async createTask(data: Record<string, unknown>): Promise<FeedTask> {
    const res = await apiClient.post<ApiResponse<{ record: FeedTask }>>(BASE + '/feed-tasks', data);
    return res.data.record;
  },

  async submitTask(id: number, expectedVersion: number): Promise<FeedTask> {
    const res = await apiClient.post<ApiResponse<{ record: FeedTask }>>(
      `${BASE}/feed-tasks/${id}/submit`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  async verifyTask(id: number, expectedVersion: number): Promise<FeedTask> {
    const res = await apiClient.post<ApiResponse<{ record: FeedTask }>>(
      `${BASE}/feed-tasks/${id}/verify`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  // Feed Logs
  async listLogs(page = 1, pageSize = 20, status?: string): Promise<PaginatedData<FeedLog>> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (status) params.status = status;
    const res = await apiClient.get<ApiResponse<PaginatedData<FeedLog>>>(BASE + '/feed-logs', { params });
    return res.data;
  },

  async createLog(data: Record<string, unknown>): Promise<FeedLog> {
    const res = await apiClient.post<ApiResponse<{ record: FeedLog }>>(BASE + '/feed-logs', data);
    return res.data.record;
  },

  async submitLog(id: number, expectedVersion: number): Promise<FeedLog> {
    const res = await apiClient.post<ApiResponse<{ record: FeedLog }>>(
      `${BASE}/feed-logs/${id}/submit`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },
};

export default feedingApi;
