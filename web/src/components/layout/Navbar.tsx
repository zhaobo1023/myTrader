'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuthStore } from '@/lib/store';

const navItems = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/market', label: 'Market' },
  { href: '/analysis', label: 'Analysis' },
  { href: '/rag', label: 'RAG' },
  { href: '/strategy', label: 'Strategy' },
];

export default function Navbar() {
  const pathname = usePathname();
  const { user, logout } = useAuthStore();

  return (
    <nav className="bg-white border-b border-gray-200">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex h-14 items-center justify-between">
          <div className="flex items-center space-x-8">
            <Link href="/dashboard" className="text-lg font-bold text-gray-900">
              myTrader
            </Link>
            <div className="hidden md:flex items-center space-x-1">
              {navItems.map((item) => (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`px-3 py-2 text-sm rounded-md transition-colors ${
                    pathname === item.href
                      ? 'bg-blue-50 text-blue-700 font-medium'
                      : 'text-gray-600 hover:text-gray-900 hover:bg-gray-50'
                  }`}
                >
                  {item.label}
                </Link>
              ))}
            </div>
          </div>

          <div className="flex items-center space-x-4">
            {user && (
              <span className="text-sm text-gray-500">
                {user.email} ({user.tier})
              </span>
            )}
            {user ? (
              <button
                onClick={logout}
                className="text-sm text-gray-600 hover:text-gray-900"
              >
                Logout
              </button>
            ) : (
              <Link
                href="/login"
                className="text-sm text-blue-600 hover:text-blue-500 font-medium"
              >
                Sign In
              </Link>
            )}
          </div>
        </div>
      </div>
    </nav>
  );
}
