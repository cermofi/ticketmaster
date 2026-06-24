import { expect, test } from '@playwright/test';

const adminEmail = process.env.E2E_ADMIN_EMAIL || 'admin@example.test';
const adminPassword = process.env.E2E_ADMIN_PASSWORD || 'ChangeMe123!';

async function login(page) {
  await page.goto('/#/');
  const loginForm = page.locator('.tm-login-form');
  await expect(loginForm).toBeVisible();
  await loginForm.locator('input:not([type="password"])').fill(adminEmail);
  await loginForm.locator('input[type="password"]').fill(adminPassword);
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.locator('.tm-page-header h1')).toHaveText('Tickets');
}

test.describe('smoke', () => {
  test('login', async ({ page }) => {
    await login(page);
  });

  test('sign-in-as-partner and back-to-admin', async ({ page }) => {
    await login(page);
    await page.getByRole('button', { name: 'Open user menu' }).click();
    await page.getByRole('menuitem', { name: 'Sign in as partner' }).click();
    await expect(page.getByRole('heading', { name: 'Sign in as partner' })).toBeVisible();
    await page.locator('#tm-partner-sign-in-user').selectOption({ index: 1 });
    await page.getByRole('button', { name: 'Sign in', exact: true }).click();
    await expect(page.locator('body.tm-partner-session')).toBeVisible();
    await page.getByRole('button', { name: 'Open user menu' }).click();
    await page.getByRole('menuitem', { name: 'Back to admin' }).click();
    await expect(page.locator('body.tm-partner-session')).toHaveCount(0);
    await expect(page.locator('.tm-page-header h1')).toHaveText('Tickets');
  });

  test('internal user creates ticket to partner', async ({ page }) => {
    await login(page);
    await page.goto('/#/tickets/new?target=partner');
    await expect(page.locator('.tm-page-header h1')).toHaveText('Create ticket to partner');
    const form = page.locator('.tm-ticket-create-form');
    await expect(form).toBeVisible();
    const title = `[SMOKE] partner ticket ${Date.now()}`;
    await form.locator('select').nth(0).selectOption({ index: 1 });
    await form.locator('select').nth(1).selectOption({ index: 1 });
    await form.locator('input[type="text"]').fill(title);
    await form.locator('.tm-field-wide textarea').fill('Playwright smoke create');
    await form.getByRole('button', { name: 'Create to partner' }).click();
    await expect(page).toHaveURL(/#\/tickets\//);
    await expect(page.getByText(title)).toBeVisible();
  });

  test('audit page loads and filters', async ({ page }) => {
    await login(page);
    await page.goto('/#/audit');
    await expect(page.locator('.tm-page-header h1')).toHaveText('Audit');
    await page.locator('#audit-action').selectOption('auth.login');
    await expect(page.locator('table tbody tr').first()).toBeVisible({ timeout: 20_000 });
  });

  test('export excel trigger', async ({ page }) => {
    await login(page);
    await page.getByRole('button', { name: 'More' }).click();
    const downloadPromise = page.waitForEvent('download', { timeout: 30_000 });
    await page.getByRole('menuitem', { name: /Export tickets \(Excel\)/i }).click();
    const download = await downloadPromise;
    expect(download.suggestedFilename()).toMatch(/\.xlsx$/i);
  });
});
