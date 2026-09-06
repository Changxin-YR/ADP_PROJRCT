import apiClient from './client';
import { ApiResponse, PaginatedData, SalesOrder } from '../types';

const BASE = '/api/v1/sales';

export const salesApi = {
  async listOrders(page = 1, pageSize = 20, status?: string): Promise<PaginatedData<SalesOrder>> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (status) params.status = status;
    const res = await apiClient.get<ApiResponse<PaginatedData<SalesOrder>>>(BASE + '/orders', { params });
    return res.data;
  },

  async getOrder(id: number): Promise<SalesOrder> {
    const res = await apiClient.get<ApiResponse<{ record: SalesOrder }>>(`${BASE}/orders/${id}`);
    return res.data.record;
  },

  async createOrder(data: Record<string, unknown>): Promise<SalesOrder> {
    const res = await apiClient.post<ApiResponse<{ record: SalesOrder }>>(BASE + '/orders', data);
    return res.data.record;
  },

  async updateOrder(id: number, data: Record<string, unknown>): Promise<SalesOrder> {
    const res = await apiClient.patch<ApiResponse<{ record: SalesOrder }>>(`${BASE}/orders/${id}`, data);
    return res.data.record;
  },

  async submitOrder(id: number, expectedVersion: number): Promise<SalesOrder> {
    const res = await apiClient.post<ApiResponse<{ record: SalesOrder }>>(
      `${BASE}/orders/${id}/submit`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  async approveOrder(id: number, expectedVersion: number): Promise<SalesOrder> {
    const res = await apiClient.post<ApiResponse<{ record: SalesOrder }>>(
      `${BASE}/orders/${id}/approve`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  async cancelOrder(id: number, expectedVersion: number): Promise<SalesOrder> {
    const res = await apiClient.post<ApiResponse<{ record: SalesOrder }>>(
      `${BASE}/orders/${id}/cancel`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  async deleteOrder(id: number): Promise<void> {
    await apiClient.delete(`${BASE}/orders/${id}`);
  },

  async listDeliveries(page = 1, pageSize = 20): Promise<PaginatedData<any>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<any>>>(
      BASE + '/deliveries',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },

  async listReceipts(page = 1, pageSize = 20): Promise<PaginatedData<any>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<any>>>(
      BASE + '/receipts',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },

  async listCustomers(page = 1, pageSize = 20): Promise<PaginatedData<any>> {
    const res = await apiClient.get<ApiResponse<PaginatedData<any>>>(
      BASE + '/customers',
      { params: { page, page_size: pageSize } }
    );
    return res.data;
  },
};

export default salesApi;
