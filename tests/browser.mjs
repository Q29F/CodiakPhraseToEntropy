// Install Python requirements and Playwright Chromium before running this file.
import assert from 'node:assert/strict'
import { Buffer } from 'node:buffer'
import { mkdir } from 'node:fs/promises'
import { join } from 'node:path'
import { test } from 'node:test'
import { chromium } from 'playwright'
import { startWorkbench } from './server.mjs'

async function download(page, format) {
  const ready = page.waitForEvent('download')
  await page.getByRole('button', { name: `Download ${format}`, exact: true }).click()
  const artifact = await ready
  assert.equal(artifact.suggestedFilename(), format === 'JSON' ? 'codiak-result.json' : 'codiak-samples.csv')
  assert.equal(await artifact.failure(), null)
  const stream = await artifact.createReadStream()
  assert.ok(stream, 'The download must contain readable data')
  const chunks = []
  for await (const chunk of stream) chunks.push(chunk)
  return Buffer.concat(chunks).toString('utf8')
}

async function calculate(page) {
  const ready = page.waitForResponse(response => new URL(response.url()).pathname === '/api/calculate' && response.request().method() === 'POST')
  await page.getByRole('button', { name: 'Calculate', exact: true }).click()
  const response = await ready
  assert.equal(response.status(), 200)
  const result = await response.json()
  await page.getByRole('table', { name: 'Field samples', exact: true }).waitFor({ state: 'visible' })
  return result
}

async function fillParameters(page, values) {
  for (const [label, value] of Object.entries(values)) {
    await page.getByLabel(label, { exact: true }).fill(String(value))
  }
}

async function assertCleared(page) {
  assert.ok(await page.getByRole('button', { name: 'Download JSON', exact: true, includeHidden: true }).isDisabled())
  assert.ok(await page.getByRole('button', { name: 'Download CSV', exact: true, includeHidden: true }).isDisabled())
  assert.equal(await page.getByRole('table', { name: 'Field samples', exact: true }).count(), 0)
}

async function screenshot(page, filename) {
  if (!process.env.CODIAK_SCREENSHOTS) return
  await mkdir(process.env.CODIAK_SCREENSHOTS, { recursive: true })
  await page.evaluate(() => globalThis.scrollTo({ top: 0, left: 0, behavior: 'instant' }))
  await page.screenshot({ path: join(process.env.CODIAK_SCREENSHOTS, filename), fullPage: true })
}

test('Codiak workbench in Chromium', { timeout: 90_000 }, async t => {
  const { origin } = await startWorkbench(t)
  const browser = await chromium.launch({ headless: true })
  t.after(() => browser.close())
  const pageErrors = []
  const consoleErrors = []
  const policyViolations = []
  const thirdPartyRequests = []
  const dialogs = []
  const calculationRequests = []

  async function createContext(options = {}) {
    const context = await browser.newContext({ acceptDownloads: true, ...options })
    context.setDefaultTimeout(5_000)
    context.setDefaultNavigationTimeout(15_000)
    await context.exposeBinding('recordPolicyViolation', (_source, details) => policyViolations.push(details))
    await context.addInitScript(() => {
      globalThis.document.addEventListener('securitypolicyviolation', event => {
        globalThis.recordPolicyViolation({ directive: event.effectiveDirective, blocked: event.blockedURI })
      })
    })
    context.on('request', request => {
      if (!/^https?:/.test(request.url())) return
      const url = new URL(request.url())
      if (url.origin !== origin) thirdPartyRequests.push(request.url())
      if (url.pathname === '/api/calculate' && request.method() === 'POST') calculationRequests.push(request)
    })
    context.on('page', page => {
      page.on('pageerror', error => pageErrors.push(error.message))
      page.on('console', message => {
        if (message.type() === 'error') consoleErrors.push(message.text())
      })
      page.on('dialog', async dialog => {
        dialogs.push(dialog.message())
        await dialog.dismiss()
      })
    })
    return context
  }

  const context = await createContext({ viewport: { width: 1440, height: 1000 } })
  const page = await context.newPage()

  await t.test('loads labelled controls with explicit calculation and disabled exports', async () => {
    const response = await page.goto(origin)
    assert.equal(response.status(), 200)
    await page.waitForLoadState('networkidle')
    assert.ok(await page.getByRole('heading', { name: 'Codiak workbench', level: 1 }).isVisible())
    assert.ok(await page.getByLabel('Phrase mode', { exact: true }).isChecked())
    assert.equal(await page.getByLabel('Phrase', { exact: true }).inputValue(), 'Codiak')
    for (const label of ['Phrase', 'u', 'v', 'y', 't']) {
      assert.ok(await page.getByLabel(label, { exact: true }).isEditable())
    }
    await assertCleared(page)
    assert.equal(calculationRequests.length, 0)
  })

  await t.test('phrase mode calculates the known phase and exports actual JSON and CSV', async () => {
    await page.getByLabel('Phrase', { exact: true }).fill('abab')
    await fillParameters(page, { u: 3, v: 4, y: 1, t: 0 })
    assert.equal(calculationRequests.length, 0, 'Editing must not calculate implicitly')
    const result = await calculate(page)
    assert.ok(Math.abs(result.phase - Math.PI / 2) < 1e-12)
    assert.deepEqual(result.phraseAnalysis, {
      length: 4, unique: 2, entropy: 1, normalizedEntropy: 0.5, phase: Math.PI / 2,
    })
    assert.deepEqual(result.parameters, { u: 3, v: 4, y: 1, t: 0 })
    assert.equal(result.samples.length, 129)
    assert.ok(Math.abs(result.samples[64].value - 5) < 1e-12)
    assert.ok(await page.getByRole('img', { name: 'Field cross-section', exact: true }).isVisible())
    const exported = await download(page, 'JSON')
    assert.deepEqual(JSON.parse(exported), result)
    assert.ok(!exported.includes('abab'), 'The source phrase must not be included in exports')
    const rows = (await download(page, 'CSV')).trim().split(/\r?\n/)
    assert.equal(rows[0], 'x,value')
    assert.equal(rows.length, 130)
    for (let index = 0; index < 129; index += 1) {
      const values = rows[index + 1].split(',').map(Number)
      assert.equal(values.length, 2)
      assert.ok(values.every(Number.isFinite))
      assert.ok(Math.abs(values[0] - result.samples[index].x) < 1e-12)
      assert.ok(Math.abs(values[1] - result.samples[index].value) < 1e-12)
    }
    await screenshot(page, 'codiak-desktop.png')
  })

  await t.test('manual phase mode updates the actual field and clears stale exports on edits', async () => {
    await page.getByLabel('Manual phase mode', { exact: true }).check()
    await assertCleared(page)
    await fillParameters(page, { Phase: Math.PI / 2, u: 3, v: 4, y: 0, t: 0 })
    const result = await calculate(page)
    assert.equal(result.phraseAnalysis, null)
    assert.ok(Math.abs(result.phase - Math.PI / 2) < 1e-12)
    assert.ok(result.samples.every(sample => Math.abs(sample.value - 5) < 1e-12))
    assert.deepEqual(JSON.parse(await download(page, 'JSON')), result)
    await page.getByLabel('u', { exact: true }).fill('101')
    await assertCleared(page)
    await page.getByRole('button', { name: 'Calculate', exact: true }).click()
    assert.ok(await page.getByRole('alert').isVisible())
    await assertCleared(page)
  })

  await t.test('reset works from the keyboard and restores the uncalculated defaults', async () => {
    await page.getByRole('button', { name: 'Reset', exact: true }).focus()
    await page.keyboard.press('Enter')
    assert.ok(await page.getByLabel('Phrase mode', { exact: true }).isChecked())
    assert.equal(await page.getByLabel('Phrase', { exact: true }).inputValue(), 'Codiak')
    for (const [label, expected] of Object.entries({ u: '1', v: '1', y: '1', t: '0' })) {
      assert.equal(await page.getByLabel(label, { exact: true }).inputValue(), expected)
    }
    await assertCleared(page)
    await page.getByLabel('Manual phase mode', { exact: true }).focus()
    await page.keyboard.press('Space')
    assert.ok(await page.getByLabel('Manual phase mode', { exact: true }).isChecked())
    assert.equal(await page.getByLabel('Phase', { exact: true }).inputValue(), '0.5')
    await page.getByRole('button', { name: 'Reset', exact: true }).click()
  })

  await t.test('an input edit cannot publish the result of an earlier in-flight request', async () => {
    let release
    let finished
    const gate = new Promise(resolve => { release = resolve })
    const done = new Promise(resolve => { finished = resolve })
    const handler = async route => {
      await gate
      try {
        await route.continue()
      } catch (error) {
        if (!route.request().failure()) throw error
      } finally {
        finished()
      }
    }
    await page.route(`${origin}/api/calculate`, handler)
    try {
      const started = page.waitForRequest(request => request.url() === `${origin}/api/calculate` && request.method() === 'POST')
      await page.getByRole('button', { name: 'Calculate', exact: true }).click()
      await started
      await page.getByLabel('Phrase', { exact: true }).fill('aaaa')
      await assertCleared(page)
      release()
      await done
      await page.waitForLoadState('networkidle')
      await assertCleared(page)
    } finally {
      release()
      await page.unroute(`${origin}/api/calculate`, handler)
    }
    const result = await calculate(page)
    assert.equal(result.phase, 0)
    assert.equal(result.phraseAnalysis.entropy, 0)
  })

  await t.test('markup in a phrase is handled as text without being exported or executed', async () => {
    const phrase = '<img src=x onerror=alert(1)>'
    await page.getByLabel('Phrase', { exact: true }).fill(phrase)
    const result = await calculate(page)
    assert.equal(await page.getByLabel('Phrase', { exact: true }).inputValue(), phrase)
    assert.equal(await page.locator('img[src="x"]').count(), 0)
    assert.equal(result.phraseAnalysis.length, phrase.length)
    assert.ok(!(await download(page, 'JSON')).includes(phrase))
  })

  await t.test('the mobile workbench calculates without horizontal page overflow', async () => {
    const mobileContext = await createContext({ viewport: { width: 320, height: 844 }, isMobile: true, hasTouch: true })
    const mobile = await mobileContext.newPage()
    await mobile.goto(origin)
    await mobile.waitForLoadState('networkidle')
    await mobile.getByLabel('Phrase', { exact: true }).fill('abab')
    await fillParameters(mobile, { u: 3, v: 4 })
    const result = await calculate(mobile)
    assert.ok(Math.abs(result.phase - Math.PI / 2) < 1e-12)
    const widths = await mobile.evaluate(() => ({
      document: globalThis.document.documentElement.scrollWidth,
      body: globalThis.document.body.scrollWidth,
    }))
    assert.ok(widths.document <= 321 && widths.body <= 321, `Mobile page overflow: ${JSON.stringify(widths)}`)
    await screenshot(mobile, 'codiak-mobile.png')
    await mobile.getByRole('button', { name: 'Reset', exact: true }).click()
    await assertCleared(mobile)
    await mobileContext.close()
  })

  await t.test('browser behavior has no security policy failures or third-party traffic', async () => {
    await page.waitForLoadState('networkidle')
    assert.deepEqual(
      { pageErrors, consoleErrors, policyViolations, thirdPartyRequests, dialogs },
      { pageErrors: [], consoleErrors: [], policyViolations: [], thirdPartyRequests: [], dialogs: [] },
    )
  })
})
