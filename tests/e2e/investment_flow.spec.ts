// E2E test: Investment flow
// Run: npx playwright test tests/e2e/investment_flow.spec.ts
import { test, expect } from '@playwright/test';

const BASE_URL = process.env.BASE_URL || 'http://localhost:3000';
const API_URL = process.env.API_URL || 'http://localhost:8000';

const TEST_USER = {
  email: `e2e-test-${Date.now()}@example.com`,
  password: 'TestPass123!',
};

test.describe('Investment Flow', () => {
  test.beforeAll(async () => {
    // Register test user via API
    const res = await fetch(`${API_URL}/api/auth/register`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(TEST_USER),
    });
    if (!res.ok) {
      // User may already exist, try login
      const loginRes = await fetch(`${API_URL}/api/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(TEST_USER),
      });
      if (!loginRes.ok) throw new Error('Failed to setup test user');
    }
  });

  test('login -> dashboard -> market -> analysis -> RAG', async ({ page }) => {
    // 1. Login
    await page.goto(`${BASE_URL}/login`);
    await page.fill('input[type="email"]', TEST_USER.email);
    await page.fill('input[type="password"]', TEST_USER.password);
    await page.click('button[type="submit"]');
    await page.waitForURL('**/dashboard', { timeout: 10000 });

    // 2. Dashboard loads
    await expect(page.locator('h1')).toContainText('Dashboard');
    expect(await page.textContent('body')).toContain('Holdings');

    // 3. Navigate to Market
    await page.click('a[href="/market"]');
    await page.waitForURL('**/market');
    await expect(page.locator('h1')).toContainText('Market');

    // 4. Search stock
    await page.fill('input[placeholder*="stock code"]', '600519');
    await page.click('button:has-text("Search")');
    await page.waitForTimeout(2000);
    expect(await page.textContent('body')).toBeTruthy();

    // 5. Navigate to Analysis
    await page.click('a[href="/analysis"]');
    await page.waitForURL('**/analysis');
    await expect(page.locator('h1')).toContainText('Analysis');

    // 6. Analyze stock
    await page.fill('input[placeholder*="stock code"]', '600519');
    await page.click('button:has-text("Analyze")');
    await page.waitForTimeout(3000);
    expect(await page.textContent('body')).toContain('Technical Analysis');

    // 7. Navigate to RAG
    await page.click('a[href="/rag"]');
    await page.waitForURL('**/rag');
    await expect(page.locator('h1')).toContainText('RAG Research');
  });

  test('public screener accessible without login', async ({ page }) => {
    await page.goto(`${BASE_URL}/public/screener`);
    await expect(page.locator('h1')).toContainText('Stock Screener');
    expect(await page.textContent('body')).toContain('RPS Rankings');
  });
});
