const state = { operations: [], tag: 'all', query: '' }
const list = document.querySelector('#operation-list')
const tags = document.querySelector('#tag-list')
const search = document.querySelector('#api-search')

function render() {
  const query = state.query.toLowerCase()
  const rows = state.operations.filter(item =>
    (state.tag === 'all' || item.tag === state.tag) &&
    (!query || `${item.method} ${item.path} ${item.summary} ${item.tag}`.toLowerCase().includes(query)),
  )
  document.querySelector('#result-count').textContent = `${rows.length} 项操作`
  list.replaceChildren(...(rows.length ? rows.map(row => {
    const article = document.createElement('article')
    article.className = 'operation'
    const method = document.createElement('span')
    method.className = `method ${row.method === 'GET' ? '' : 'write'}`
    method.textContent = row.method
    const path = document.createElement('div')
    path.className = 'path'
    const code = document.createElement('code')
    code.textContent = row.path
    const summary = document.createElement('span')
    summary.textContent = row.summary
    path.append(code, summary)
    const tag = document.createElement('span')
    tag.className = 'tag'
    tag.textContent = row.tag
    article.append(method, path, tag)
    return article
  }) : [Object.assign(document.createElement('p'), { className: 'empty', textContent: '没有匹配的接口。' })]))
}

function renderTags(values) {
  const all = ['all', ...values]
  tags.replaceChildren(...all.map(value => {
    const button = document.createElement('button')
    button.type = 'button'
    button.textContent = value === 'all' ? '全部' : value
    button.className = value === state.tag ? 'active' : ''
    button.addEventListener('click', () => { state.tag = value; renderTags(values); render() })
    return button
  }))
}

search.addEventListener('input', event => { state.query = event.target.value; render() })

fetch('./openapi.json')
  .then(response => { if (!response.ok) throw new Error('OpenAPI unavailable'); return response.json() })
  .then(spec => {
    state.operations = Object.entries(spec.paths).flatMap(([path, methods]) =>
      Object.entries(methods).map(([method, operation]) => ({
        path,
        method: method.toUpperCase(),
        summary: operation.summary || operation.description || '',
        tag: operation.tags?.[0] || path.split('/')[3] || 'other',
      })),
    )
    document.querySelector('#operation-count').textContent = state.operations.length
    renderTags([...new Set(state.operations.map(item => item.tag))].sort())
    render()
  })
  .catch(() => { list.textContent = '无法读取 OpenAPI 契约，请确认 openapi.json 已生成。' })
