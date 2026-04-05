'use client';

import { useEffect, useState } from 'react';
import Navbar from '@/components/layout/Navbar';
import apiClient from '@/lib/api-client';
import { useAuthStore } from '@/lib/store';
import { useRouter } from 'next/navigation';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

interface UserItem {
  id: number;
  email: string;
  tier: string;
  role: string;
  is_active: boolean;
  created_at: string;
}

export default function AdminPage() {
  const router = useRouter();
  const { user } = useAuthStore();
  const queryClient = useQueryClient();
  const [page, setPage] = useState(1);

  useEffect(() => {
    if (!user || user.role !== 'admin') router.push('/dashboard');
  }, [user, router]);

  const { data: usersData, isLoading } = useQuery({
    queryKey: ['admin-users', page],
    queryFn: () =>
      apiClient.get('/api/admin/users', { params: { page, page_size: 20 } }).then((r) => r.data),
    enabled: !!user && user.role === 'admin',
  });

  const toggleTier = useMutation({
    mutationFn: ({ userId, tier }: { userId: number; tier: string }) =>
      apiClient.put(`/api/admin/users/${userId}/tier`, null, { params: { tier } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-users'] }),
  });

  const toggleActive = useMutation({
    mutationFn: ({ userId, isActive }: { userId: number; isActive: boolean }) =>
      apiClient.put(`/api/admin/users/${userId}/active`, null, { params: { is_active: isActive } }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['admin-users'] }),
  });

  if (!user || user.role !== 'admin') return null;

  return (
    <div className="min-h-screen bg-gray-50">
      <Navbar />
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-6">Admin - User Management</h1>

        <div className="bg-white rounded-lg border">
          <div className="px-4 py-3 border-b flex items-center justify-between">
            <h2 className="text-lg font-medium">Users</h2>
            <span className="text-sm text-gray-500">
              {usersData ? `Total: ${usersData.total}` : ''}
            </span>
          </div>

          {isLoading ? (
            <div className="p-8 text-center text-gray-400">Loading...</div>
          ) : usersData && usersData.data.length > 0 ? (
            <>
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className="border-b bg-gray-50">
                      <th className="text-left px-4 py-2 font-medium text-gray-500">ID</th>
                      <th className="text-left px-4 py-2 font-medium text-gray-500">Email</th>
                      <th className="text-left px-4 py-2 font-medium text-gray-500">Tier</th>
                      <th className="text-left px-4 py-2 font-medium text-gray-500">Role</th>
                      <th className="text-left px-4 py-2 font-medium text-gray-500">Status</th>
                      <th className="text-left px-4 py-2 font-medium text-gray-500">Created</th>
                      <th className="text-right px-4 py-2 font-medium text-gray-500">Actions</th>
                    </tr>
                  </thead>
                  <tbody>
                    {usersData.data.map((u: UserItem) => (
                      <tr key={u.id} className="border-b last:border-0 hover:bg-gray-50">
                        <td className="px-4 py-2 font-mono">{u.id}</td>
                        <td className="px-4 py-2">{u.email}</td>
                        <td className="px-4 py-2">
                          <span className={`text-xs px-2 py-0.5 rounded-full ${
                            u.tier === 'pro' ? 'bg-purple-50 text-purple-700' : 'bg-gray-100 text-gray-600'
                          }`}>
                            {u.tier}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-gray-500">{u.role}</td>
                        <td className="px-4 py-2">
                          <span className={`text-xs px-2 py-0.5 rounded-full ${
                            u.is_active ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
                          }`}>
                            {u.is_active ? 'Active' : 'Disabled'}
                          </span>
                        </td>
                        <td className="px-4 py-2 text-gray-400 text-xs">
                          {u.created_at?.split('T')[0]}
                        </td>
                        <td className="px-4 py-2 text-right space-x-2">
                          <button
                            onClick={() => toggleTier.mutate({
                              userId: u.id,
                              tier: u.tier === 'pro' ? 'free' : 'pro',
                            })}
                            className="text-xs text-blue-600 hover:text-blue-800"
                          >
                            {u.tier === 'pro' ? 'Demote' : 'Upgrade'}
                          </button>
                          <button
                            onClick={() => toggleActive.mutate({
                              userId: u.id,
                              isActive: !u.is_active,
                            })}
                            className={`text-xs hover:underline ${
                              u.is_active ? 'text-red-600' : 'text-green-600'
                            }`}
                          >
                            {u.is_active ? 'Disable' : 'Enable'}
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {/* Pagination */}
              <div className="px-4 py-3 border-t flex justify-center gap-2">
                <button
                  onClick={() => setPage((p) => Math.max(1, p - 1))}
                  disabled={page <= 1}
                  className="px-3 py-1 text-sm border rounded hover:bg-gray-50 disabled:opacity-50"
                >
                  Prev
                </button>
                <span className="px-3 py-1 text-sm text-gray-500">Page {page}</span>
                <button
                  onClick={() => setPage((p) => p + 1)}
                  disabled={usersData.data.length < 20}
                  className="px-3 py-1 text-sm border rounded hover:bg-gray-50 disabled:opacity-50"
                >
                  Next
                </button>
              </div>
            </>
          ) : (
            <div className="p-8 text-center text-gray-400">No users found</div>
          )}
        </div>
      </main>
    </div>
  );
}
