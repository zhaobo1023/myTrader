import apiClient from './api-client';

export interface AuthUser {
  id: number;
  email: string;
  tier: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

// Matches backend TokenResponse
interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
}

export async function login(email: string, password: string): Promise<AuthUser> {
  const { data } = await apiClient.post<TokenResponse>('/api/auth/login', {
    email,
    password,
  });
  localStorage.setItem('access_token', data.access_token);
  localStorage.setItem('refresh_token', data.refresh_token);
  return getMe();
}

export async function register(email: string, password: string): Promise<AuthUser> {
  const { data } = await apiClient.post<TokenResponse>('/api/auth/register', {
    email,
    password,
  });
  localStorage.setItem('access_token', data.access_token);
  localStorage.setItem('refresh_token', data.refresh_token);
  return getMe();
}

export function logout(): void {
  localStorage.removeItem('access_token');
  localStorage.removeItem('refresh_token');
}

export async function getMe(): Promise<AuthUser> {
  const { data } = await apiClient.get<AuthUser>('/api/auth/me');
  return data;
}
