'use client';

import { useState, useEffect } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useAuthStore } from '@/lib/store';

const navItems = [
  { href: '/dashboard', label: 'Dashboard' },
  { href: '/market', label: 'Market' },
  { href: '/analysis', label: 'Analysis' },
  { href: '/strategy', label: 'Strategy' },
];

interface NavbarProps {
  searchBar?: React.ReactNode;
}

export default function Navbar({ searchBar }: NavbarProps) {
  const pathname = usePathname();
  const { user, logout } = useAuthStore();
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  return (
    <nav className="bg-white border-b border-gray-200">
      <div className="flex items-center justify-between max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-14 relative">
        {/* Left: logo + nav links */}
        <div className="flex items-center space-x-8 flex-shrink-0">
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

        {/* Center: search bar - absolutely centered */}
        {searchBar && (
          <div className="absolute left-1/2 -translate-x-1/2 w-full max-w-xl px-4">
            {searchBar}
          </div>
        )}

        {/* Right: user controls */}
        <div className="flex items-center space-x-4 flex-shrink-0">
          {mounted && user && (
            <span className="text-sm text-gray-500">
              {user.email} ({user.tier})
            </span>
          )}
          {mounted ? (
            user ? (
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
            )
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
    </nav>
  );
}
