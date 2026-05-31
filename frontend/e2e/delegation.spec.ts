/**
 * DelegationMonitor 集成拨测
 *
 * 面板行为依赖 SSE 事件驱动，通过 unit test 覆盖纯函数逻辑。
 * 此处只验证页面加载基线。
 *
 * 用法: npx playwright test --config frontend/playwright.config.ts e2e/delegation.spec.ts
 */
import { test, expect } from '@playwright/test';

test.describe('DelegationMonitor smoke', () => {
  test('页面正常加载', async ({ page }) => {
    await page.goto('/');
    await page.waitForSelector('#root', { timeout: 10000 });
    const app = page.locator('#root');
    await expect(app).toBeVisible();
  });
});
