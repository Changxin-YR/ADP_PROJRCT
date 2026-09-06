import apiClient from './client';
import { ApiResponse, RegistrationOptions, RegistrationRequest, RegistrationResult, User } from '../types';

const AUTH_BASE = '/api/v1/auth';

export interface LoginRequest {
  identifier: string;
  password: string;
}

export interface ChangePasswordRequest {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

export const authApi = {
  /**
   * Login with identifier (phone/username) and password.
   * The backend uses cookie-based sessions (adp_session).
   * Flow: GET /csrf -> POST /login (sets cookie) -> GET /me
   */
  async login(credentials: LoginRequest): Promise<User> {
    // First fetch a fresh CSRF token (also establishes session cookie)
    await apiClient.fetchCsrfToken();

    // Login - backend sets adp_session cookie in response
    const response = await apiClient.post<ApiResponse<{ user: User; session?: { token?: string } }>>(
      `${AUTH_BASE}/login`,
      credentials
    );

    const sessionToken = (response.data as any).session?.token;
    if (sessionToken) await apiClient.setSession(sessionToken);

    // Refresh CSRF after login (token is bound to new session)
    await apiClient.fetchCsrfToken();

    return response.data.user || response.data as unknown as User;
  },

  async getRegistrationOptions(): Promise<RegistrationOptions> {
    const response = await apiClient.get<ApiResponse<RegistrationOptions>>(`${AUTH_BASE}/register/options`);
    return response.data;
  },

  async register(data: RegistrationRequest): Promise<RegistrationResult> {
    await apiClient.fetchCsrfToken();
    const response = await apiClient.post<ApiResponse<RegistrationResult>>(`${AUTH_BASE}/register`, data);
    const sessionToken = response.data.session?.token;
    if (sessionToken) await apiClient.setSession(sessionToken);
    await apiClient.fetchCsrfToken();
    return response.data;
  },

  async getApplication(): Promise<{ application: Record<string, unknown> | null }> {
    const response = await apiClient.get<ApiResponse<{ application: Record<string, unknown> | null }>>(`${AUTH_BASE}/application`);
    return response.data;
  },

  /**
   * Logout and clear session
   */
  async logout(): Promise<void> {
    try {
      await apiClient.post(`${AUTH_BASE}/logout`);
    } catch {
      // Even if API call fails, clear local session
    } finally {
      await apiClient.logout();
    }
  },

  /**
   * Get current user profile
   */
  async getMe(): Promise<User> {
    const response = await apiClient.get<ApiResponse<User>>(`${AUTH_BASE}/me`);
    return (response.data as any).user || response.data;
  },

  /**
   * Change password
   */
  async changePassword(data: ChangePasswordRequest): Promise<void> {
    await apiClient.post(`${AUTH_BASE}/password/change`, data);
  },

  /**
   * Check if user has valid session
   */
  async checkSession(): Promise<boolean> {
    try {
      const hasSession = await apiClient.hasSession();
      if (!hasSession) return false;
      await authApi.getMe();
      return true;
    } catch {
      return false;
    }
  },
};

export default authApi;
