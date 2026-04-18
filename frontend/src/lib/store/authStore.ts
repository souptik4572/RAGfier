import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface AuthState {
  accessToken: string | null;
  tenantId: string | null;
  userId: string | null;
  email: string | null;
  setAuth: (params: {
    accessToken: string;
    tenantId: string;
    userId: string;
    email: string;
  }) => void;
  clearAuth: () => void;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set) => ({
      accessToken: null,
      tenantId: null,
      userId: null,
      email: null,
      setAuth: ({ accessToken, tenantId, userId, email }) =>
        set({ accessToken, tenantId, userId, email }),
      clearAuth: () =>
        set({ accessToken: null, tenantId: null, userId: null, email: null }),
    }),
    {
      name: 'ragfier-auth',
    }
  )
);
