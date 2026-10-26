import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({headless: true,
  args: ['--no-proxy-server', '--host-resolver-rules=MAP *.example.test 127.0.0.1']});
const base = process.env.TEST_BASE;
const vault = base.replace('cluster.example.test', 'vault.example.test');
try {
  const anonymous = await browser.newContext({ignoreHTTPSErrors: true});
  const anonymousPage = await anonymous.newPage();
  const denied = await anonymousPage.goto(vault + '/admin/users');
  assert.equal(denied.status(), 401);
  await anonymous.close();
  for (const role of ['owner1', 'owner2', 'reader']) {
    const context = await browser.newContext({ignoreHTTPSErrors: true});
    const page = await context.newPage();
    await page.goto(base + '/cluster-admin/?role=' + role);
    if (role === 'reader') {
      const frame = page.frameLocator('iframe');
      await frame.locator('#status').filter({hasText: 'NS8-Administrator'}).waitFor();
      assert.equal(new URL(page.url()).hostname, 'cluster.example.test');
      console.log('Browser reader: no admin navigation');
    } else {
      await page.waitForURL(vault + '/admin/', {timeout: 30000});
      await page.locator('#config-form').waitFor();
      const cookies = await context.cookies(vault + '/admin/');
      assert(cookies.some(cookie => cookie.name === 'VW_ADMIN' && cookie.httpOnly && cookie.secure));
      assert(await page.locator('#input_sso_enabled').isDisabled());
      assert(await page.locator('#input_sso_enabled').isChecked());
      assert.notEqual(await page.locator('#input_admin_token').getAttribute('readonly'), null);
      if (role === 'owner1') {
        const result = await page.evaluate(async data => {
          const response = await fetch('/admin/config', {method: 'POST',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
          return response.status;
        }, {
          password_hints_allowed: false, sso_enabled: false, sso_only: false,
          admin_token: 'must-not-override-ns8', signups_allowed: true
        });
        assert.equal(result, 200);
        const control = await context.newPage();
        await control.goto(base + '/test-control');
        const restart = await control.evaluate(async () =>
          (await fetch('/test-restart', {method: 'POST'})).status);
        assert.equal(restart, 200);
        await control.close();
        await page.reload();
      }
      assert(!(await page.locator('#input_password_hints_allowed').isChecked()));
      assert(await page.locator('#input_sso_enabled').isChecked());
      const users = await page.evaluate(async () => {
        const response = await fetch('/admin/users');
        return {status: response.status, users: await response.json()};
      });
      assert.equal(users.status, 200);
      assert(Array.isArray(users.users));
      console.log('Browser ' + role + ': automatic admin login, users and persistent settings OK');
    }
    await context.close();
  }
} finally {
  await browser.close();
}
