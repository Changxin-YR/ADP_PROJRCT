import apiClient from './client';
import { ApiResponse, PaginatedData, PurchaseOrder } from '../types';

const BASE = '/api/v1/purchase';

export const purchaseApi = {
  async listOrders(page = 1, pageSize = 20, status?: string): Promise<PaginatedData<PurchaseOrder>> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (status) params.status = status;
    const res = await apiClient.get<ApiResponse<PaginatedData<PurchaseOrder>>>(BASE + '/orders', { params });
    return res.data;
  },

  async getOrder(id: number): Promise<PurchaseOrder> {
    const res = await apiClient.get<ApiResponse<{ record: PurchaseOrder }>>(`${BASE}/orders/${id}`);
    return res.data.record;
  },

  async createOrder(data: Record<string, unknown>): Promise<PurchaseOrder> {
    const res = await apiClient.post<ApiResponse<{ record: PurchaseOrder }>>(BASE + '/orders', data);
    return res.data.record;
  },

  async updateOrder(id: number, data: Record<string, unknown>): Promise<PurchaseOrder> {
    const res = await apiClient.patch<ApiResponse<{ record: PurchaseOrder }>>(`${BASE}/orders/${id}`, data);
    return res.data.record;
  },

  async submitOrder(id: number, expectedVersion: number): Promise<PurchaseOrder> {
    const res = await apiClient.post<ApiResponse<{ record: PurchaseOrder }>>(
      `${BASE}/orders/${id}/submit`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  async approveOrder(id: number, expectedVersion: number): Promise<PurchaseOrder> {
    const res = await apiClient.post<ApiResponse<{ record: PurchaseOrder }>>(
      `${BASE}/orders/${id}/approve`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  async cancelOrder(id: number, expectedVersion: number): Promise<PurchaseOrder> {
    const res = await apiClient.post<ApiResponse<{ record: PurchaseOrder }>>(
      `${BASE}/orders/${id}/cancel`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  async deleteOrder(id: number): Promise<void> {
    await apiClient.delete(`${BASE}/orders/${id}`);
  },

  async listPayments(page = 1, pageSize = 20): Promise<PaginatedData<any>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<any>>>(
      BASE + '/payments',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },

  async listSuppliers(page = 1, pageSize = 20): Promise<PaginatedData<any>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<any>>>(
      BASE + '/suppliers',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },
};

export default purchaseApi;
