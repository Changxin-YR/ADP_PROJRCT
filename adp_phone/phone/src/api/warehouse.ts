import apiClient from './client';
import { ApiResponse, PaginatedData, WarehouseDocument, StockAlert } from '../types';

const BASE = '/api/v1/warehouse';

export const warehouseApi = {
  // Receipts (入库)
  async listReceipts(page = 1, pageSize = 20, status?: string): Promise<PaginatedData<WarehouseDocument>> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (status) params.status = status;
    const res = await apiClient.get<ApiResponse<PaginatedData<WarehouseDocument>>>(BASE + '/receipts', { params });
    return res.data;
  },

  async createReceipt(data: Record<string, unknown>): Promise<WarehouseDocument> {
    const res = await apiClient.post<ApiResponse<{ record: WarehouseDocument }>>(BASE + '/receipts', data);
    return res.data.record;
  },

  async submitReceipt(id: number, expectedVersion: number): Promise<WarehouseDocument> {
    const res = await apiClient.post<ApiResponse<{ record: WarehouseDocument }>>(
      `${BASE}/receipts/${id}/submit`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  // Issue Requests (领料申请)
  async listIssueRequests(page = 1, pageSize = 20): Promise<PaginatedData<WarehouseDocument>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<WarehouseDocument>>>(
      BASE + '/issue-requests',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },

  // Issues (出库)
  async listIssues(page = 1, pageSize = 20, status?: string): Promise<PaginatedData<WarehouseDocument>> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (status) params.status = status;
    const res = await apiClient.get<ApiResponse<PaginatedData<WarehouseDocument>>>(BASE + '/issues', { params });
    return res.data;
  },

  async createIssue(data: Record<string, unknown>): Promise<WarehouseDocument> {
    const res = await apiClient.post<ApiResponse<{ record: WarehouseDocument }>>(BASE + '/issues', data);
    return res.data.record;
  },

  // Transfers (调拨)
  async listTransfers(page = 1, pageSize = 20): Promise<PaginatedData<WarehouseDocument>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<WarehouseDocument>>>(
      BASE + '/transfers',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },

  // Stocktakes (盘点)
  async listStocktakes(page = 1, pageSize = 20): Promise<PaginatedData<WarehouseDocument>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<WarehouseDocument>>>(
      BASE + '/stocktakes',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },

  // Returns (退库)
  async listReturns(page = 1, pageSize = 20): Promise<PaginatedData<WarehouseDocument>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<WarehouseDocument>>>(
      BASE + '/returns',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },

  // Scraps (报废)
  async listScraps(page = 1, pageSize = 20): Promise<PaginatedData<WarehouseDocument>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<WarehouseDocument>>>(
      BASE + '/scraps',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },

  // Alerts
  async listAlerts(): Promise<StockAlert[]> {
    const res = await apiClient.get<ApiResponse<{ items: StockAlert[] }>>(BASE + '/alerts');
    return res.data.items;
  },

  async handleAlert(alertKey: string, actionCode: string, resolutionNote: string): Promise<any> {
    const res = await apiClient.post<ApiResponse<any>>(
      `${BASE}/alerts/${encodeURIComponent(alertKey)}/handle`,
      { alert_key: alertKey, action_code: actionCode, resolution_note: resolutionNote }
    );
    return res.data;
  },
};

export default warehouseApi;
