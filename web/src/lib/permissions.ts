/**
 * Route permissions configuration
 */

export interface RoutePermission {
  tier?: ('free' | 'pro')[];
  role?: ('user' | 'admin')[];
}

export interface RouteConfig {
  href: string;
  permission?: RoutePermission;
}

// Routes that require specific permissions
export const PROTECTED_ROUTES: Record<string, RoutePermission> = {
  '/data-health': {
    role: ['admin'],
  },
  '/admin': {
    role: ['admin'],
  },
};

// Navigation items with their permission requirements
export const NAV_PERMISSIONS: Record<string, RoutePermission> = {
  '/data-health': {
    role: ['admin'],
  },
};

/**
 * Check if a user has permission to access a route
 */
export function hasPermission(
  userTier: string | null,
  userRole: string | null,
  permission?: RoutePermission
): boolean {
  if (!permission) return true;

  const { tier, role } = permission;

  // Check tier requirement
  if (tier && tier.length > 0) {
    const normalizedTier = userTier?.toLowerCase();
    if (!normalizedTier || !tier.includes(normalizedTier as 'free' | 'pro')) {
      return false;
    }
  }

  // Check role requirement
  if (role && role.length > 0) {
    const normalizedRole = userRole?.toLowerCase();
    if (!normalizedRole || !role.includes(normalizedRole as 'user' | 'admin')) {
      return false;
    }
  }

  return true;
}
