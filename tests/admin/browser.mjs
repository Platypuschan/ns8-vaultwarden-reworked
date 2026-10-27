import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({headless: true,
  args: ['--no-proxy-server', '--host-resolver-rules=MAP *.example.test 127.0.0.1']});
const base = process.env.TEST_BASE;
const vault = base.replace('cluster.example.test', 'vault.example.test');
const cluster = base + '/cluster-admin/';

// The admin page must open in the application frame, the cluster manager stays.
async function adminFrame(page) {
  for (let i = 0; i < 300; i++) {
    const frame = page.frames().find(f => f.url() === vault + '/admin/');
    if (frame) {
      try { await frame.locator('#config-form').waitFor(); }
      catch (error) {
        console.log('Admin frame diagnosis:', await frame.title(), await frame.locator('form').evaluateAll(forms => forms.map(f => f.id)));
        console.log('Admin frame message:', (await frame.locator('body').innerText()).slice(0, 180));
        throw error;
      }
      assert(page.url().startsWith(cluster));
      return frame;
    }
    await page.waitForTimeout(100);
  }
  throw new Error('Admin page did not open in the application frame');
}

try {
  const anonymous = await browser.newContext({ignoreHTTPSErrors: true});
  const anonymousPage = await anonymous.newPage();
  const denied = await anonymousPage.goto(vault + '/admin/users');
  assert.equal(denied.status(), 403);
  await anonymous.close();

  // Direct SSO link: the web vault goes to the IdP without asking for an email.
  const direct = await browser.newContext({ignoreHTTPSErrors: true});
  const directPage = await direct.newPage();
  const authorize = directPage.waitForRequest(r => r.url().startsWith(vault + '/identity/connect/authorize?'),
    {timeout: 60000});
  await directPage.goto(vault + '/#/sso?identifier=00000000-01DC-01DC-01DC-000000000000');
  assert.equal(new URL((await authorize).url()).searchParams.get('client_id'), 'web');
  console.log('Browser SSO link: no email step before the IdP');
  await direct.close();

  for (const role of ['owner1', 'owner2', 'reader', 'tab']) {
    const context = await browser.newContext({ignoreHTTPSErrors: true});
    const page = await context.newPage();
    await page.goto(cluster + '?role=' + role);
    if (role === 'reader') {
      const frame = page.frameLocator('iframe').first();
      await frame.locator('#status').filter({hasText: 'NS8-Administrator'}).waitFor();
      assert.equal(new URL(page.url()).hostname, 'cluster.example.test');
      console.log('Browser reader: no admin navigation');
    } else if (role === 'tab') {
      const frame = page.frameLocator('iframe').first();
      await frame.locator('#status').filter({hasText: 'neuem Tab'}).waitFor();
      const [tab] = await Promise.all([context.waitForEvent('page'), frame.locator('#open').click()]);
      await tab.waitForURL(vault + '/admin/', {timeout: 30000});
      await tab.locator('#config-form').waitFor();
      assert(page.url().startsWith(cluster));
      console.log('Browser tab: not embeddable, admin opens in a new tab, cluster manager stays');
    } else {
      let frame = await adminFrame(page);
      assert.equal(context.pages().length, 1);
      const cookies = await context.cookies(vault + '/admin/');
      assert(cookies.some(cookie => cookie.name === 'NS8_ADMIN' && cookie.httpOnly && cookie.secure));
      assert(await frame.locator('#input_sso_enabled').isDisabled());
      assert(await frame.locator('#input_sso_enabled').isChecked());
      assert.notEqual(await frame.locator('#input_admin_token').getAttribute('readonly'), null);
      assert.equal(await frame.locator('#input_admin_token').inputValue(), '********');
      assert.equal(await frame.locator('#input_sso_client_secret').inputValue(), '********');
      if (role === 'owner1') {
        const result = await frame.evaluate(async data => {
          const response = await fetch('/admin/config', {method: 'POST',
            headers: {'Content-Type': 'application/json'}, body: JSON.stringify(data)});
          return response.status;
        }, {
          password_hints_allowed: false, sso_enabled: false, sso_only: false,
          admin_token: 'must-not-override-ns8', signups_allowed: true,
          allowed_iframe_ancestors: ''
        });
        assert.equal(result, 200);
        const control = await context.newPage();
        await control.goto(base + '/test-control');
        const restart = await control.evaluate(async () =>
          (await fetch('/test-restart', {method: 'POST'})).status);
        assert.equal(restart, 200);
        await control.close();
        await page.reload();
        // A saved empty value must not stop the cluster manager from embedding the page.
        frame = await adminFrame(page);
      }
      assert(!(await frame.locator('#input_password_hints_allowed').isChecked()));
      assert(await frame.locator('#input_sso_enabled').isChecked());
      const users = await frame.evaluate(async () => {
        const response = await fetch('/admin/users');
        return {status: response.status, users: await response.json()};
      });
      assert.equal(users.status, 200);
      assert(Array.isArray(users.users));
      console.log('Browser ' + role + ': automatic admin login in the application frame, users and persistent settings OK');
    }
    await context.close();
  }
} finally {
  await browser.close();
}
