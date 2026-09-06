import apiClient from './client';
import { ApiResponse, WorkbenchSummary, WorkItem, AppNotification } from '../types';

const SUMMARY_BASE = '/api/v1/workbench';
const BASE = '/api/v1';

export const workbenchApi = {
  async getSummary(): Promise<WorkbenchSummary> {
    const res = await apiClient.get<ApiResponse<WorkbenchSummary>>(SUMMARY_BASE + '/summary');
    return res.data;
  },

  async listWorkItems(page = 1, status?: string): Promise<{ items: WorkItem[]; total: number }> {
    const params: Record<string, string | number> = { page, page_size: 20 };
    if (status) params.status = status;
    const res = await apiClient.get<ApiResponse<{ items: WorkItem[]; total: number }>>(
      BASE + '/work-items', { params }
    );
    return res.data;
  },

  async claimWorkItem(id: number): Promise<WorkItem> {
    const res = await apiClient.patch<ApiResponse<{ work_item: WorkItem }>>(
      `${BASE}/work-items/${id}`,
      { action: 'claim' }
    );
    return res.data.work_item;
  },

  async completeWorkItem(id: number, data?: Record<string, unknown>): Promise<WorkItem> {
    const res = await apiClient.patch<ApiResponse<{ work_item: WorkItem }>>(
      `${BASE}/work-items/${id}`,
      { ...(data || {}), action: 'complete' }
    );
    return res.data.work_item;
  },

  async listNotifications(page = 1, includeHistory = false): Promise<{ items: AppNotification[]; total: number }> {
    const res = await apiClient.get<ApiResponse<{ items: AppNotification[]; total: number }>>(
      BASE + '/notifications',
      { params: { page, page_size: 20, include_history: includeHistory } }
    );
    return res.data;
  },

  async markNotificationRead(id: number): Promise<void> {
    await apiClient.patch(`${BASE}/notifications/${id}`, { status: 'read' });
  },

  async closeNotification(id: number, conclusion?: string): Promise<void> {
    await apiClient.patch(`${BASE}/notifications/${id}`, { status: 'closed', conclusion });
  },
};

export default workbenchApi;
