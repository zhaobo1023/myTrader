import { create } from 'zustand';
import { AuthUser, getMe, logout as authLogout } from './auth';

interface AuthState {
  user: AuthUser | null;
  fetchUser: () => Promise<void>;
  setUser: (user: AuthUser | null) => void;
  logout: () => void;
}

export const useAuthStore = create<AuthState>((set) => ({
  user: null,

  fetchUser: async () => {
    try {
      const user = await getMe();
      set({ user });
    } catch {
      set({ user: null });
    }
  },

  setUser: (user) => set({ user }),

  logout: () => {
    authLogout();
    set({ user: null });
    // [AUTH-DISABLED] redirect disabled during dev — re-enable before prod
    // if (typeof window !== 'undefined') {
    //   window.location.href = '/login';
    // }
  },
}));
