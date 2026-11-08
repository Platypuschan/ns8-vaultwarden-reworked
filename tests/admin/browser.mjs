import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({headless: true,
  args: ['--no-proxy-server', '--host-resolver-rules=MAP *.example.test 127.0.0.1, MAP *.co.uk 127.0.0.1']});
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

  for (const role of ['owner1', 'owner2', 'reader', 'tab', 'public-suffix']) {
    const context = await browser.newContext({ignoreHTTPSErrors: true});
    const page = await context.newPage();
    const manager = role === 'public-suffix' ? cluster.replace('cluster.example.test', 'cluster.two.co.uk') : cluster;
    await page.goto(manager + '?role=' + role);
    if (role === 'reader') {
      const frame = page.frameLocator('iframe').first();
      await frame.locator('#status').filter({hasText: 'NS8-Administrator'}).waitFor();
      assert.equal(new URL(page.url()).hostname, 'cluster.example.test');
      console.log('Browser reader: no admin navigation');
    } else if (role === 'public-suffix') {
      // User decision 29.10.2026: no tab fallback beside the embedded page.
      // Across two distinct sites the Strict cookie stays unavailable.
      const suffixVault = vault.replace('vault.example.test', 'vault.one.co.uk');
      const application = page.frameLocator('iframe').first();
      let embedded;
      for (let i = 0; i < 100; i++) {
        embedded = page.frames().find(frame => frame.url() === suffixVault + '/admin/');
        if (embedded) break;
        await page.waitForTimeout(100);
      }
      assert(embedded);
      await embedded.locator('#config-form').waitFor();
      assert(!(await application.locator('#open').isVisible()));
      const blocked = await embedded.evaluate(async () => (await fetch('/admin/users')).status);
      assert.equal(blocked, 403, 'Strict cookie must be unavailable across two distinct co.uk sites');
      assert(page.url().startsWith(manager));
      console.log('Browser public suffix: embedded without fallback, cross-site Strict cookie rejected');
    } else if (role === 'tab') {
      const frame = page.frameLocator('iframe').first();
      await frame.locator('#status').filter({hasText: 'neuem Tab'}).waitFor();
      const [tab] = await Promise.all([context.waitForEvent('page'), frame.locator('#open').click()]);
      await tab.waitForURL(vault + '/admin/', {timeout: 30000});
      await tab.locator('#config-form').waitFor();
      assert(page.url().startsWith(cluster));
      // The module page renews the session of the other tab without its cookie
      await page.waitForTimeout(20000);
      assert.equal(await tab.evaluate(async () => (await fetch('/admin/users')).status), 200);
      console.log('Browser tab: not embeddable, admin opens in a new tab, cluster manager stays, session renewed');
    } else {
      let frame = await adminFrame(page);
      assert.equal(context.pages().length, 1);
      // Only the admin frame, over the whole application area
      const application = page.frameLocator('iframe').first();
      for (const selector of ['h1', '#status', '#open'])
        assert(!(await application.locator(selector).isVisible()), selector + ' must be hidden');
      assert(!(await application.locator('#warning').isVisible()), 'no warning bar over the admin frame');
      const notices = await page.evaluate(() => window.notifications.map(n => n.type + ':' + n.description));
      if (role === 'owner1') {
        assert(notices.some(n => n.startsWith('warning:') && n.includes('Zugriffswiderruf')), notices.join());
      } else {
        assert.deepEqual(notices, []);
      }
      const area = await page.locator('iframe').first().boundingBox();
      const admin = await application.locator('#admin-frame').boundingBox();
      assert(Math.abs(admin.width - area.width) <= 1 && Math.abs(admin.height - area.height) <= 1,
        `admin frame ${admin.width}x${admin.height} must fill ${area.width}x${area.height}`);
      const cookies = await context.cookies(vault + '/admin/');
      assert(cookies.some(cookie => cookie.name === 'NS8_ADMIN' && cookie.httpOnly && cookie.secure));
      assert(await frame.locator('#input_sso_enabled').isDisabled());
      assert(await frame.locator('#input_sso_enabled').isChecked());
      assert.notEqual(await frame.locator('#input_admin_token').getAttribute('readonly'), null);
      // The admin page warns about a plain text token unless the field starts with $argon2
      assert.equal(await frame.locator('#input_admin_token').inputValue(), '$argon2id$********');
      assert(await frame.locator('#admin_token_warning').evaluate(el => el.classList.contains('d-none')), 'plain text ADMIN_TOKEN warning must stay hidden');
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
      if (role === 'owner2') {
        // Renewed beyond the session lifetime while the page is open
        await page.waitForTimeout(20000);
        assert.equal(await frame.evaluate(async () => (await fetch('/admin/users')).status), 200);
        // Without the NS8 right to run open-admin, no new ticket: the session ends
        const control = await context.newPage();
        await control.goto(base + '/test-control');
        assert.equal(await control.evaluate(async () => (await fetch('/test-revoke?role=owner2', {method: 'POST'})).status), 200);
        await control.close();
        await page.waitForTimeout(20000);
        assert.equal(await frame.evaluate(async () => (await fetch('/admin/users')).status), 403);
        const ended = await page.evaluate(() => window.notifications.map(n => n.type + ':' + n.description));
        assert(ended.some(n => n.startsWith('warning:') && n.includes('nicht verlängert')), ended.join());
        console.log('Browser owner2: session renewed while open, ended after the NS8 right was revoked');
      }
      console.log('Browser ' + role + ': automatic admin login in the application frame, users and persistent settings OK');
    }
    await context.close();
  }
} finally {
  await browser.close();
}
