import apiClient from './api-client';

export interface AuthUser {
  id: number;
  username: string;
  display_name: string | null;
  email: string | null;
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

export async function login(username: string, password: string): Promise<AuthUser> {
  const { data } = await apiClient.post<TokenResponse>('/api/auth/login', {
    username,
    password,
  });
  localStorage.setItem('access_token', data.access_token);
  localStorage.setItem('refresh_token', data.refresh_token);
  return getMe();
}

export async function register(
  username: string,
  password: string,
  inviteCode: string,
  displayName?: string,
): Promise<AuthUser> {
  const { data } = await apiClient.post<TokenResponse>('/api/auth/register', {
    username,
    password,
    invite_code: inviteCode,
    display_name: displayName || undefined,
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
