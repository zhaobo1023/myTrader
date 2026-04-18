'use client';

import { useEffect } from 'react';
import { useRouter } from 'next/navigation';
import { useAuthStore } from '@/lib/store';
import { PROTECTED_ROUTES, hasPermission } from '@/lib/permissions';

interface ProtectedRouteProps {
  children: React.ReactNode;
  routePath: string;
}

export function ProtectedRoute({ children, routePath }: ProtectedRouteProps) {
  const router = useRouter();
  const user = useAuthStore((state) => state.user);

  useEffect(() => {
    // Check if route requires permission
    const permission = PROTECTED_ROUTES[routePath];

    if (permission) {
      const hasAccess = hasPermission(
        user?.tier ?? null,
        user?.role ?? null,
        permission
      );

      if (!hasAccess) {
        // Redirect to a page the user can access
        router.replace('/sentiment');
      }
    }
  }, [user, routePath, router]);

  // While checking permissions or if user data is not loaded yet
  // For now, we'll render children and redirect in useEffect if needed
  return <>{children}</>;
}
