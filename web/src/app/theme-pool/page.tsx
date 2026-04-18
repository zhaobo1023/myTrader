'use client';

import { redirect } from 'next/navigation';

export default function ThemePoolPage() {
  redirect('/strategy?tab=theme');
}
