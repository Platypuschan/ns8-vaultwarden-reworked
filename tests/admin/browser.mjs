import assert from 'node:assert/strict';
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright');
const browser = await chromium.launch({headless: true,
  args: ['--no-proxy-server', '--host-resolver-rules=MAP *.example.test 127.0.0.1, MAP *.co.uk 127.0.0.1']});
const base = process.env.TEST_BASE;
const vault = base.replace('cluster.example.test', 'vault.example.test');
const cluster = base + '/cluster-admin/';
// Optional: VW_SCREENSHOTS=<directory> keeps a picture of each module page
async function shot(page, name) {
  if (process.env.VW_SCREENSHOTS) await page.screenshot({path: `${process.env.VW_SCREENSHOTS}/${name}.png`});
}

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

  for (const role of process.env.VW_ONLY === 'panel' ? [] : ['owner1', 'owner2', 'reader', 'tab', 'public-suffix']) {
    const context = await browser.newContext({ignoreHTTPSErrors: true});
    const page = await context.newPage();
    const manager = role === 'public-suffix' ? cluster.replace('cluster.example.test', 'cluster.two.co.uk') : cluster;
    await page.goto(manager + '?page=admin&role=' + role);
    if (role === 'reader') {
      const application = page.frameLocator('iframe').first();
      await application.locator('.bx--inline-notification--error').waitFor();
      assert(!page.frames().some(f => f.url() === vault + '/admin/'), 'a reader must not get the admin page');
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
      assert(!(await application.getByRole('button', {name: 'Open in new tab'}).isVisible()));
      const blocked = await embedded.evaluate(async () => (await fetch('/admin/users')).status);
      assert.equal(blocked, 403, 'Strict cookie must be unavailable across two distinct co.uk sites');
      assert(page.url().startsWith(manager));
      console.log('Browser public suffix: embedded without fallback, cross-site Strict cookie rejected');
    } else if (role === 'tab') {
      const frame = page.frameLocator('iframe').first();
      await frame.getByRole('button', {name: 'Open in new tab'}).waitFor();
      const [tab] = await Promise.all([context.waitForEvent('page'), frame.getByRole('button', {name: 'Open in new tab'}).click()]);
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
      // The admin page sits in the module page next to the NS8 menu
      const application = page.frameLocator('iframe').first();
      await application.locator('.bx--side-nav__link-text').filter({hasText: 'Settings'}).first().waitFor();
      const admin = await application.locator('iframe[name=vaultwarden-admin-frame]').boundingBox();
      assert(admin.width > 600 && admin.height > 400, `admin frame ${admin.width}x${admin.height} too small`);
      await shot(page, 'advanced-admin-' + role);
      const warning = application.locator('.bx--inline-notification--warning');
      if (role === 'owner1') {
        await warning.filter({hasText: 'access revocation is disturbed'}).waitFor();
      } else {
        assert.equal(await warning.count(), 0, 'no warning expected');
      }
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
        await application.locator('.bx--inline-notification--warning').filter({hasText: 'cannot be renewed'}).waitFor();
        console.log('Browser owner2: session renewed while open, ended after the NS8 right was revoked');
      }
      console.log('Browser ' + role + ': automatic admin login in the application frame, users and persistent settings OK');
    }
    await context.close();
  }

  // The native pages, against the real runtime through the module actions
  {
    const context = await browser.newContext({ignoreHTTPSErrors: true, viewport: {width: 1500, height: 1100}});
    const page = await context.newPage();
    const open = async (name, title) => {
      await page.goto(cluster + '?page=' + name + '&role=owner2');
      const app = page.frameLocator('iframe').first();
      await app.locator('h2').filter({hasText: title}).waitFor();
      return app;
    };
    const settled = app => app.locator('.bx--skeleton__text').first().waitFor({state: 'detached'}).catch(() => {});
    const confirm = app => app.locator('.bx--modal.is-visible').getByRole('button', {name: /^(Confirm|Reset to defaults|Delete organization)$/}).click();
    let app = await open('settings', 'Settings');
    await settled(app);
    await app.getByText('General settings').first().waitFor();
    // Managed values (single sign-on, domain, admin token) are not offered at all
    const text = await app.locator('body').innerText();
    for (const hidden of ['OpenID Connect', 'SSO', 'Admin token', 'Domain URL', 'Yubikey'])
      assert(!text.includes(hidden), hidden + ' must not be offered');
    assert.deepEqual((await app.locator('.bx--accordion__title').allInnerTexts()), [
      'General settings', 'Advanced settings', 'Global Duo settings (users can override them)',
      'SMTP email settings', 'Email 2FA settings']);
    // Save, reload, see it again; reset restores the default
    const limit = app.getByLabel('Per-user attachment storage limit (KB)');
    await limit.fill('12345');
    await app.getByRole('button', {name: 'Save'}).click();
    await app.getByText('Settings saved.').waitFor();
    await shot(page, 'settings-saved');
    app = await open('settings', 'Settings');
    await settled(app);
    assert.equal(await app.getByLabel('Per-user attachment storage limit (KB)').inputValue(), '12345');
    await app.getByRole('button', {name: 'Reset to defaults'}).click();
    await confirm(app);
    await app.getByText('Settings reset to defaults.').waitFor();
    assert.equal(await app.getByLabel('Per-user attachment storage limit (KB)').inputValue(), '');
    // Mail mode choice: off, cluster smarthost (unavailable here), custom
    await app.getByText('SMTP email settings').click();
    const modes = await app.locator('select').first().locator('option').allInnerTexts();
    assert.deepEqual(modes, ['Email disabled', 'Cluster smarthost (the rest custom)', 'Custom']);
    console.log('Browser settings: managed fields hidden, save/reset against the real runtime');

    app = await open('users', 'Users');
    await settled(app);
    const row = address => app.locator('tr').filter({hasText: address});
    await row('one@example.test').waitFor();
    await shot(page, 'users');
    await row('one@example.test').getByRole('button', {name: 'Disable'}).click();
    await confirm(app);
    await row('one@example.test').locator('.bx--tag').filter({hasText: 'Disabled'}).waitFor();
    await row('one@example.test').getByRole('button', {name: 'Enable'}).click();
    await confirm(app);
    await row('one@example.test').getByRole('button', {name: 'Disable'}).waitFor();
    await row('one@example.test').getByRole('button', {name: 'Delete user'}).click();
    await confirm(app);
    await row('one@example.test').waitFor({state: 'detached'});
    await row('two@example.test').waitFor();
    console.log('Browser users: disable, enable and delete against the real runtime');

    app = await open('organizations', 'Organizations');
    await settled(app);
    await app.getByText('No organizations.').waitFor();
    await shot(page, 'organizations');

    app = await open('diagnostics', 'Diagnostics');
    await settled(app);
    await app.getByText('Server version').waitFor();
    await app.getByText('Server time (UTC)').waitFor();
    await shot(page, 'diagnostics');
    console.log('Browser diagnostics: versions, network and time shown');
    await context.close();
  }
} finally {
  await browser.close();
}
