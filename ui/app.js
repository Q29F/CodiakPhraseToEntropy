'use strict';

(() => {
  const byId = id => document.getElementById(id)
  const form = byId('calculator')
  const calculateButton = byId('calculate')
  const resetButton = byId('reset-inputs')
  const inputs = {
    phrase: byId('phrase'), phase: byId('phase'),
    u: byId('u'), v: byId('v'), y: byId('y'), t: byId('t'),
  }
  const resultPanel = document.querySelector('.result-panel')
  const snapshotPanel = byId('snapshot')
  const emptyPanel = byId('empty-result')
  const errorBox = byId('error')
  const status = byId('status')
  const jsonButton = byId('download-json')
  const csvButton = byId('download-csv')
  const token = document.querySelector('meta[name="csrf-token"]')?.content ?? ''
  const hasToken = /^[a-f0-9]{64}$/.test(token)
  const svgNamespace = 'http://www.w3.org/2000/svg'
  const formatters = new Map()
  let generation = 0
  let activeController = null
  let snapshot = null
  let chartWidth = 0

  class DisplayError extends Error {}

  function formatNumber(value, digits = 4) {
    if (value === 0) return '0'
    if (Math.abs(value) < 0.0001 || Math.abs(value) >= 1_000_000) return value.toExponential(3)
    if (!formatters.has(digits)) formatters.set(digits, new Intl.NumberFormat('en-US', { maximumFractionDigits: digits }))
    return formatters.get(digits).format(value)
  }

  function setMetric(id, value) {
    const output = byId(id)
    const text = formatNumber(value)
    output.textContent = text
    output.classList.toggle('compact-value', text.length > 8)
  }

  function mode() {
    return form.querySelector('input[name="mode"]:checked').value
  }

  function syncMode() {
    const phraseMode = mode() === 'phrase'
    byId('phrase-controls').hidden = !phraseMode
    byId('phase-controls').hidden = phraseMode
    inputs.phrase.disabled = !phraseMode
    inputs.phase.disabled = phraseMode
    byId('phrase-count').textContent = `${Array.from(inputs.phrase.value).length.toLocaleString('en-US')} / 2,048`
  }

  function setBusy(busy) {
    resultPanel.setAttribute('aria-busy', String(busy))
    calculateButton.disabled = busy || !hasToken
  }

  function clearError() {
    errorBox.hidden = true
    errorBox.textContent = ''
    for (const input of Object.values(inputs)) input.removeAttribute('aria-invalid')
  }

  function showError(message) {
    errorBox.hidden = false
    errorBox.textContent = message
  }

  function invalidate(message = 'Inputs changed. Calculate to update the result.') {
    generation += 1
    activeController?.abort()
    activeController = null
    snapshot = null
    snapshotPanel.hidden = true
    emptyPanel.hidden = false
    jsonButton.disabled = true
    csvButton.disabled = true
    byId('samples-body').replaceChildren()
    byId('expression').textContent = ''
    byId('field-chart').replaceChildren()
    for (const id of ['phase-result', 'entropy-result', 'normalized-result', 'length-result', 'unique-result']) byId(id).textContent = ''
    byId('result-mode').textContent = 'Ready to calculate'
    byId('export-note').textContent = 'Calculate to create an export.'
    clearError()
    setBusy(false)
    status.textContent = message
  }

  function readNumber(name, minimum, maximum) {
    const input = inputs[name]
    const value = input.valueAsNumber
    if (!input.value.trim() || !Number.isFinite(value) || value < minimum || value > maximum) {
      input.setAttribute('aria-invalid', 'true')
      input.focus()
      const label = name === 'phase' ? 'Phase' : name
      throw new DisplayError(`${label} must be a finite number from ${minimum} to ${maximum}.`)
    }
    return value
  }

  function readPayload() {
    const selectedMode = mode()
    const payload = { mode: selectedMode }
    if (selectedMode === 'phrase') {
      const phrase = inputs.phrase.value
      if (Array.from(phrase).length > 2048) {
        inputs.phrase.setAttribute('aria-invalid', 'true')
        inputs.phrase.focus()
        throw new DisplayError('Phrase must contain at most 2,048 Unicode code points.')
      }
      payload.phrase = phrase
    } else {
      payload.phase = readNumber('phase', 0, Math.PI)
    }
    payload.u = readNumber('u', -100, 100)
    payload.v = readNumber('v', -100, 100)
    payload.y = readNumber('y', -10, 10)
    payload.t = readNumber('t', -100, 100)
    return payload
  }

  function finiteInRange(value, minimum, maximum) {
    return typeof value === 'number' && Number.isFinite(value) && value >= minimum && value <= maximum
  }

  function responseSnapshot(value) {
    const invalid = () => { throw new DisplayError('The local server returned an unexpected result. Reload the page and try again.') }
    if (value === null || typeof value !== 'object' || Array.isArray(value)) invalid()
    if (!finiteInRange(value.phase, 0, Math.PI) || typeof value.expression !== 'string' || value.expression.length > 2048) invalid()
    const parameters = value.parameters
    if (parameters === null || typeof parameters !== 'object' || Array.isArray(parameters)) invalid()
    for (const [name, bound] of [['u', 100], ['v', 100], ['y', 10], ['t', 100]]) {
      if (!finiteInRange(parameters[name], -bound, bound)) invalid()
    }
    if (!Array.isArray(value.samples) || value.samples.length !== 129) invalid()
    const samples = value.samples.map(sample => {
      if (sample === null || typeof sample !== 'object' || Array.isArray(sample)) invalid()
      if (!finiteInRange(sample.x, -Math.PI, Math.PI) || !finiteInRange(sample.value, -142, 142)) invalid()
      return { x: sample.x, value: sample.value }
    })
    let phraseAnalysis = null
    if (value.phraseAnalysis !== null) {
      const analysis = value.phraseAnalysis
      if (!analysis || typeof analysis !== 'object' || Array.isArray(analysis)) invalid()
      if (!Number.isInteger(analysis.length) || analysis.length < 0 || analysis.length > 2048) invalid()
      if (!Number.isInteger(analysis.unique) || analysis.unique < 0 || analysis.unique > analysis.length) invalid()
      if (!finiteInRange(analysis.entropy, 0, 11) || !finiteInRange(analysis.normalizedEntropy, 0, 1) || analysis.phase !== value.phase) invalid()
      phraseAnalysis = {
        length: analysis.length, unique: analysis.unique, entropy: analysis.entropy,
        normalizedEntropy: analysis.normalizedEntropy, phase: analysis.phase,
      }
    }
    return {
      phase: value.phase,
      expression: value.expression,
      parameters: { u: parameters.u, v: parameters.v, y: parameters.y, t: parameters.t },
      phraseAnalysis,
      samples,
    }
  }

  function svgElement(name, attributes = {}, text = '') {
    const element = document.createElementNS(svgNamespace, name)
    for (const [key, value] of Object.entries(attributes)) element.setAttribute(key, String(value))
    if (text) element.textContent = text
    return element
  }

  function drawCurve(result) {
    const svg = byId('field-chart')
    const width = svg.parentElement.clientWidth || 720
    const height = width < 420 ? 250 : 300
    chartWidth = width
    svg.setAttribute('viewBox', `0 0 ${width} ${height}`)
    const left = 76
    const right = 20
    const top = 20
    const bottom = 50
    const plotWidth = width - left - right
    const plotHeight = height - top - bottom
    const middle = top + plotHeight / 2
    const peak = Math.max(...result.samples.map(sample => Math.abs(sample.value)))
    const range = peak === 0 ? 1 : peak * 1.1
    const title = svgElement('title', { id: 'curve-title' }, 'Field cross-section')
    const description = svgElement('desc', { id: 'curve-description' }, `129 signed field samples across x from minus pi to pi, with phase ${formatNumber(result.phase)} radians. Exact values are in the Field samples table.`)
    svg.replaceChildren(title, description)
    for (const [tick, y] of [[range, top], [0, middle], [-range, top + plotHeight]]) {
      svg.append(svgElement('line', { class: tick === 0 ? 'plot-zero' : 'plot-grid', x1: left, x2: width - right, y1: y, y2: y }))
      const label = tick !== 0 && Math.abs(tick) < 0.001 ? tick.toExponential(1) : formatNumber(tick, 2)
      svg.append(svgElement('text', { class: 'plot-label', x: left - 11, y: y + 4, 'text-anchor': 'end' }, label))
    }
    for (const [fraction, label] of [[0, '−π'], [0.25, '−π/2'], [0.5, '0'], [0.75, 'π/2'], [1, 'π']]) {
      const x = left + fraction * plotWidth
      svg.append(svgElement('line', { class: 'plot-grid', x1: x, x2: x, y1: top, y2: top + plotHeight }))
      svg.append(svgElement('text', { class: 'plot-label', x, y: height - 27, 'text-anchor': 'middle' }, label))
    }
    const path = result.samples.map((sample, index) => {
      const x = left + (sample.x + Math.PI) / (2 * Math.PI) * plotWidth
      const y = middle - sample.value / range * plotHeight / 2
      return `${index === 0 ? 'M' : 'L'}${x.toFixed(2)} ${y.toFixed(2)}`
    }).join(' ')
    svg.append(svgElement('path', { class: 'plot-line', d: path }))
    svg.append(svgElement('text', { class: 'plot-axis-name', x: left + plotWidth / 2, y: height - 5, 'text-anchor': 'middle' }, 'x'))
  }

  function renderResult(result) {
    emptyPanel.hidden = true
    snapshotPanel.hidden = false
    setMetric('phase-result', result.phase)
    byId('expression').textContent = result.expression
    const analysis = result.phraseAnalysis
    byId('entropy-card').hidden = analysis === null
    byId('manual-card').hidden = analysis !== null
    byId('phrase-metrics').hidden = analysis === null
    byId('normalization-note').hidden = analysis === null
    if (analysis !== null) {
      setMetric('entropy-result', analysis.entropy)
      setMetric('normalized-result', analysis.normalizedEntropy)
      setMetric('length-result', analysis.length)
      setMetric('unique-result', analysis.unique)
    }
    byId('result-mode').textContent = analysis === null ? 'Manual phase' : 'Phrase analysis'
    const parameters = result.parameters
    byId('parameter-summary').textContent = `u = ${formatNumber(parameters.u)}, v = ${formatNumber(parameters.v)}, y = ${formatNumber(parameters.y)}, t = ${formatNumber(parameters.t)}`
    drawCurve(result)
    const rows = document.createDocumentFragment()
    for (const sample of result.samples) {
      const row = document.createElement('tr')
      for (const value of [sample.x, sample.value]) {
        const cell = document.createElement('td')
        cell.textContent = formatNumber(value, 8)
        row.append(cell)
      }
      rows.append(row)
    }
    byId('samples-body').replaceChildren(rows)
    byId('export-note').textContent = '129 samples. Display values are rounded; downloads retain full numeric values.'
    jsonButton.disabled = false
    csvButton.disabled = false
  }

  async function calculate() {
    if (!hasToken) return
    invalidate('Checking inputs…')
    let payload
    try {
      payload = readPayload()
    } catch (error) {
      showError(error instanceof DisplayError ? error.message : 'Check the input values and try again.')
      status.textContent = 'Calculation needs valid inputs.'
      return
    }
    const requestGeneration = generation
    const controller = new AbortController()
    activeController = controller
    let timedOut = false
    const timeout = setTimeout(() => {
      timedOut = true
      controller.abort()
    }, 10_000)
    setBusy(true)
    byId('result-mode').textContent = 'Calculating'
    status.textContent = 'Calculating with the local Python process…'
    try {
      const response = await fetch('/api/calculate', {
        method: 'POST',
        credentials: 'same-origin',
        cache: 'no-store',
        redirect: 'error',
        headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': token },
        body: JSON.stringify(payload),
        signal: controller.signal,
      })
      if (requestGeneration !== generation) return
      if (response.status === 403) throw new DisplayError('Reload this page to refresh the local session, then calculate again.')
      if (response.status === 429) throw new DisplayError('The local server is busy. Wait a moment, then select Calculate again.')
      const body = await response.json()
      if (requestGeneration !== generation) return
      if (!response.ok) {
        const message = typeof body?.error === 'string' && body.error.length <= 160 ? body.error : 'The local server could not complete this calculation.'
        throw new DisplayError(message)
      }
      const result = responseSnapshot(body)
      if (requestGeneration !== generation) return
      renderResult(result)
      snapshot = result
      status.textContent = 'Calculation complete. 129 field samples are ready.'
    } catch (error) {
      if (requestGeneration !== generation) return
      const message = timedOut
        ? 'The calculation timed out. Check that the local Python process is running, then try again.'
        : error instanceof DisplayError
          ? error.message
          : 'The local Python process could not be reached. Check that it is running, then try again.'
      showError(message)
      byId('result-mode').textContent = 'Calculation stopped'
      status.textContent = 'No result is available for these inputs.'
    } finally {
      clearTimeout(timeout)
      if (requestGeneration === generation) {
        activeController = null
        setBusy(false)
      }
    }
  }

  function download(content, type, filename) {
    try {
      const url = URL.createObjectURL(new Blob([content], { type }))
      const link = document.createElement('a')
      link.href = url
      link.download = filename
      document.body.append(link)
      link.click()
      link.remove()
      setTimeout(() => URL.revokeObjectURL(url), 1_000)
      status.textContent = `${filename} download started.`
    } catch {
      showError('The download could not start. Try again in this browser.')
    }
  }

  form.addEventListener('input', () => {
    syncMode()
    invalidate()
  })
  form.addEventListener('submit', event => {
    event.preventDefault()
    calculate()
  })
  resetButton.addEventListener('click', () => {
    form.reset()
    syncMode()
    invalidate('Inputs reset. Select Calculate to create a new result.')
  })
  jsonButton.addEventListener('click', () => {
    if (snapshot === null) return
    download(`${JSON.stringify(snapshot, null, 2)}\n`, 'application/json', 'codiak-result.json')
  })
  csvButton.addEventListener('click', () => {
    if (snapshot === null) return
    const rows = ['x,value', ...snapshot.samples.map(sample => `${sample.x},${sample.value}`)]
    download(`${rows.join('\r\n')}\r\n`, 'text/csv;charset=utf-8', 'codiak-samples.csv')
  })

  const chartContainer = byId('field-chart').parentElement
  const chartObserver = new ResizeObserver(() => {
    if (snapshot !== null && chartContainer.clientWidth > 0 && chartContainer.clientWidth !== chartWidth) drawCurve(snapshot)
  })
  chartObserver.observe(chartContainer)

  syncMode()
  setBusy(false)
  if (!hasToken) showError('Open this page through the local Python workbench server, then reload it.')
})()
