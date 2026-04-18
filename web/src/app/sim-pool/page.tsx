'use client';

import { redirect } from 'next/navigation';

export default function SimPoolPage() {
  redirect('/portfolio?tab=sim');
}
