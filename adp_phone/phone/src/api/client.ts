import axios, { AxiosInstance, AxiosRequestConfig, AxiosResponse, InternalAxiosRequestConfig } from 'axios';
import * as SecureStore from 'expo-secure-store';
import AsyncStorage from '@react-native-async-storage/async-storage';

// 生产入口已从 IP 直连改为共享域名 23331.cloud/adp；IP 直连会被 Nginx 断开。
const DEFAULT_API_BASE_URL = 'https://23331.cloud/adp';
const BASE_URL = (process.env.EXPO_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL).replace(/\/+$/, '');
const CSRF_TOKEN_KEY = 'csrf_token';
const SESSION_KEY = 'adp_session';

// Offline queue item
interface QueueItem {
  id: string;
  config: AxiosRequestConfig;
  timestamp: number;
}

class ApiClient {
  private client: AxiosInstance;
  private csrfToken: string | null = null;
  private sessionCookie: string | null = null;
  private offlineQueue: QueueItem[] = [];
  private readonly ready: Promise<void>;

  constructor() {
    this.client = axios.create({
      baseURL: BASE_URL,
      timeout: 30000,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
        'X-ADP-Client': 'mobile',
      },
    });

    this.setupInterceptors();
    this.ready = Promise.all([this.loadOfflineQueue(), this.loadSession()]).then(() => undefined);
  }

  private async loadSession(): Promise<void> {
    try {
      this.sessionCookie = await SecureStore.getItemAsync(SESSION_KEY);
      this.csrfToken = await SecureStore.getItemAsync(CSRF_TOKEN_KEY);
    } catch {
      // Ignore errors on load
    }
  }

  private setupInterceptors(): void {
    // Request interceptor - attach session cookie and CSRF token
    this.client.interceptors.request.use(
      async (config: InternalAxiosRequestConfig) => {
        await this.ready;
        // Add session cookie
        if (this.sessionCookie) {
          config.headers.Cookie = `adp_session=${this.sessionCookie}`;
        }

        // Add CSRF token for write operations
        const writeMethods = ['post', 'put', 'patch', 'delete'];
        if (config.method && writeMethods.includes(config.method.toLowerCase())) {
          if (!this.csrfToken) {
            await this.fetchCsrfToken();
          }
          if (this.csrfToken) {
            config.headers['X-CSRF-Token'] = this.csrfToken;
          }
        }

        return config;
      },
      (error) => Promise.reject(error)
    );

    // Response interceptor
    this.client.interceptors.response.use(
      (response: AxiosResponse) => {
        // Capture session cookie from Set-Cookie header
        const setCookie = response.headers['set-cookie'];
        if (setCookie) {
          const match = Array.isArray(setCookie)
            ? setCookie.find(c => c.includes('adp_session'))
            : setCookie;
          if (match) {
            const cookieValue = match.split(';')[0].replace('adp_session=', '');
            if (cookieValue) {
              this.sessionCookie = cookieValue;
              SecureStore.setItemAsync(SESSION_KEY, cookieValue);
            }
          }
        }
        return response;
      },
      async (error) => {
        const originalRequest = error.config;

        // Handle 401 - session expired, redirect to login
        if (error.response?.status === 401 && !originalRequest._retry) {
          originalRequest._retry = true;
          await this.clearSession();
          return Promise.reject(error);
        }

        // Handle 403 (CSRF invalid) - refresh CSRF and retry once
        if (error.response?.status === 403 && !originalRequest._csrfRetry) {
          const code = error.response?.data?.code;
          if (code === 'CSRF_INVALID' || code === 'FORBIDDEN') {
            originalRequest._csrfRetry = true;
            this.csrfToken = null;
            await this.fetchCsrfToken();
            if (this.csrfToken) {
              originalRequest.headers['X-CSRF-Token'] = this.csrfToken;
            }
            return this.client(originalRequest);
          }
        }

        // Handle network error - add to offline queue
        if (!error.response && error.code === 'ERR_NETWORK') {
          await this.addToOfflineQueue(originalRequest);
        }

        return Promise.reject(error);
      }
    );
  }

  async fetchCsrfToken(): Promise<void> {
    await this.ready;
    try {
      const config: AxiosRequestConfig = {};
      if (this.sessionCookie) {
        config.headers = { Cookie: `adp_session=${this.sessionCookie}` };
      }
      const response = await axios.get(`${BASE_URL}/api/v1/auth/csrf`, config);
      const token = response.data?.data?.csrf_token;
      if (token) {
        this.csrfToken = token;
        await SecureStore.setItemAsync(CSRF_TOKEN_KEY, token);
      }
      // Also capture session cookie if returned
      const setCookie = response.headers['set-cookie'];
      if (setCookie) {
        const match = Array.isArray(setCookie)
          ? setCookie.find((c: string) => c.includes('adp_session'))
          : setCookie;
        if (match) {
          const cookieValue = match.split(';')[0].replace('adp_session=', '');
          if (cookieValue) {
            this.sessionCookie = cookieValue;
            await SecureStore.setItemAsync(SESSION_KEY, cookieValue);
          }
        }
      }
    } catch (error) {
      console.warn('Failed to fetch CSRF token:', error);
    }
  }

  private async clearSession(): Promise<void> {
    await SecureStore.deleteItemAsync(SESSION_KEY);
    await SecureStore.deleteItemAsync(CSRF_TOKEN_KEY);
    this.sessionCookie = null;
    this.csrfToken = null;
  }

  // --- Offline Queue ---
  private async addToOfflineQueue(config: AxiosRequestConfig): Promise<void> {
    const item: QueueItem = {
      id: `${Date.now()}_${Math.random().toString(36).slice(2)}`,
      config: {
        method: config.method,
        url: config.url,
        data: config.data,
        params: config.params,
      },
      timestamp: Date.now(),
    };
    this.offlineQueue.push(item);
    await this.saveOfflineQueue();
  }

  private async saveOfflineQueue(): Promise<void> {
    await AsyncStorage.setItem('offline_queue', JSON.stringify(this.offlineQueue));
  }

  private async loadOfflineQueue(): Promise<void> {
    try {
      const data = await AsyncStorage.getItem('offline_queue');
      if (data) {
        this.offlineQueue = JSON.parse(data);
      }
    } catch {
      this.offlineQueue = [];
    }
  }

  async processOfflineQueue(): Promise<void> {
    await this.ready;
    const queue = [...this.offlineQueue];
    this.offlineQueue = [];
    await this.saveOfflineQueue();

    for (const item of queue) {
      try {
        await this.client(item.config);
      } catch (error) {
        this.offlineQueue.push(item);
      }
    }

    if (this.offlineQueue.length > 0) {
      await this.saveOfflineQueue();
    }
  }

  getOfflineQueueSize(): number {
    return this.offlineQueue.length;
  }

  // --- Session Management ---
  async setSession(cookie: string): Promise<void> {
    this.sessionCookie = cookie;
    await SecureStore.setItemAsync(SESSION_KEY, cookie);
  }

  async logout(): Promise<void> {
    await this.clearSession();
  }

  async hasSession(): Promise<boolean> {
    await this.ready;
    const session = await SecureStore.getItemAsync(SESSION_KEY);
    return !!session;
  }

  // --- Public API Methods ---
  async get<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.get<T>(url, config);
    return response.data;
  }

  async post<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.post<T>(url, data, config);
    return response.data;
  }

  async put<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.put<T>(url, data, config);
    return response.data;
  }

  async patch<T>(url: string, data?: unknown, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.patch<T>(url, data, config);
    return response.data;
  }

  async delete<T>(url: string, config?: AxiosRequestConfig): Promise<T> {
    const response = await this.client.delete<T>(url, config);
    return response.data;
  }
}

export const apiClient = new ApiClient();
export default apiClient;
