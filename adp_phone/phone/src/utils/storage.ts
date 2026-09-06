import * as SecureStore from 'expo-secure-store';

const KEYS = {
  SESSION: 'adp_session',
  CSRF_TOKEN: 'csrf_token',
  USER_DATA: 'user_data',
} as const;

export async function getSession(): Promise<string | null> {
  return SecureStore.getItemAsync(KEYS.SESSION);
}

export async function setSession(value: string): Promise<void> {
  await SecureStore.setItemAsync(KEYS.SESSION, value);
}

export async function getCsrfToken(): Promise<string | null> {
  return SecureStore.getItemAsync(KEYS.CSRF_TOKEN);
}

export async function setCsrfToken(value: string): Promise<void> {
  await SecureStore.setItemAsync(KEYS.CSRF_TOKEN, value);
}

export async function getUserData(): Promise<string | null> {
  return SecureStore.getItemAsync(KEYS.USER_DATA);
}

export async function setUserData(value: string): Promise<void> {
  await SecureStore.setItemAsync(KEYS.USER_DATA, value);
}

export async function clearAll(): Promise<void> {
  await SecureStore.deleteItemAsync(KEYS.SESSION);
  await SecureStore.deleteItemAsync(KEYS.CSRF_TOKEN);
  await SecureStore.deleteItemAsync(KEYS.USER_DATA);
}
