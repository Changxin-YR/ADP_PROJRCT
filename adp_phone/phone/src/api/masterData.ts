import apiClient from './client';
import { ApiResponse, PaginatedData, Pond, Material, Supplier, Customer } from '../types';

const BASE = '/api/v1/master-data';

export const masterDataApi = {
  // Ponds
  async listPonds(page = 1, pageSize = 20, search?: string): Promise<PaginatedData<Pond>> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (search) params.search = search;
    const res = await apiClient.get<ApiResponse<PaginatedData<Pond>>>(BASE + '/ponds', { params });
    return res.data;
  },

  async getPond(id: number): Promise<Pond> {
    const res = await apiClient.get<ApiResponse<{ record: Pond }>>(`${BASE}/ponds/${id}`);
    return res.data.record;
  },

  async createPond(data: Record<string, unknown>): Promise<Pond> {
    const res = await apiClient.post<ApiResponse<Pond>>(BASE + '/ponds', data);
    return res.data;
  },

  async updatePond(id: number, data: Record<string, unknown>): Promise<Pond> {
    const res = await apiClient.patch<ApiResponse<{ record: Pond }>>(`${BASE}/ponds/${id}`, data);
    return res.data.record;
  },

  async submitPond(id: number, expectedVersion: number): Promise<Pond> {
    const res = await apiClient.post<ApiResponse<{ record: Pond }>>(
      `${BASE}/ponds/${id}/submit`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  async verifyPond(id: number, expectedVersion: number): Promise<Pond> {
    const res = await apiClient.post<ApiResponse<{ record: Pond }>>(
      `${BASE}/ponds/${id}/verify`,
      { expected_version: expectedVersion }
    );
    return res.data.record;
  },

  // Materials
  async listMaterials(page = 1, pageSize = 20, search?: string): Promise<PaginatedData<Material>> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (search) params.search = search;
    const res = await apiClient.get<ApiResponse<PaginatedData<Material>>>(BASE + '/materials', { params });
    return res.data;
  },

  async getMaterial(id: number): Promise<Material> {
    const res = await apiClient.get<ApiResponse<{ record: Material }>>(`${BASE}/materials/${id}`);
    return res.data.record;
  },

  async createMaterial(data: Record<string, unknown>): Promise<Material> {
    const res = await apiClient.post<ApiResponse<Material>>(BASE + '/materials', data);
    return res.data;
  },

  // Suppliers
  async listSuppliers(page = 1, pageSize = 20, search?: string): Promise<PaginatedData<Supplier>> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (search) params.search = search;
    const res = await apiClient.get<ApiResponse<PaginatedData<Supplier>>>(BASE + '/suppliers', { params });
    return res.data;
  },

  // Customers
  async listCustomers(page = 1, pageSize = 20, search?: string): Promise<PaginatedData<Customer>> {
    const params: Record<string, string | number> = { page, page_size: pageSize };
    if (search) params.search = search;
    const res = await apiClient.get<ApiResponse<PaginatedData<Customer>>>(BASE + '/customers', { params });
    return res.data;
  },

  // Farms
  async listFarms(): Promise<any> {
    const res = await apiClient.get<ApiResponse<any>>(BASE + '/farms');
    return res.data;
  },

  // Areas
  async listAreas(): Promise<any> {
    const res = await apiClient.get<ApiResponse<any>>(BASE + '/areas');
    return res.data;
  },

  // Pond Groups
  async listPondGroups(): Promise<any> {
    const res = await apiClient.get<ApiResponse<any>>(BASE + '/pond-groups');
    return res.data;
  },

  // Settings
  async getSettings(): Promise<any> {
    const res = await apiClient.get<ApiResponse<any>>(BASE + '/settings');
    return res.data;
  },
};

export default masterDataApi;
