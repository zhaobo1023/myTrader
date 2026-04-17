import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/lib/store';

/**
 * Hook that requires authentication.
 * Redirects to /login if not authenticated.
 * Returns user when ready.
 */
export function useRequireAuth() {
  const router = useRouter();
  const { user, fetchUser } = useAuthStore();

  useEffect(() => {
    if (!user) {
      fetchUser().catch(() => {
        router.push('/login');
      });
    }
  }, [user, fetchUser, router]);

  return user;
}
