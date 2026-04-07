import http from 'http'
import logger from '@overleaf/logger'
import DocumentUpdaterHandler from '../../../../app/src/Features/DocumentUpdater/DocumentUpdaterHandler.mjs'
import ProjectEntityHandler from '../../../../app/src/Features/Project/ProjectEntityHandler.mjs'

const RESEARCHKIT_URL =
  process.env.RESEARCHKIT_URL || 'http://researchkit:3020'

const parsedUrl = new URL(RESEARCHKIT_URL)

async function _getProjectFiles(projectId) {
  try {
    // Ensure we capture the latest in-editor changes before building the agent workspace snapshot.
    await DocumentUpdaterHandler.promises.flushProjectToMongo(projectId)
  } catch (err) {
    logger.warn(
      { err, projectId },
      'Failed to flush project docs before fetching ResearchKit files'
    )
  }

  try {
    const docs = await ProjectEntityHandler.promises.getAllDocs(projectId)
    const files = {}
    for (const [path, doc] of Object.entries(docs)) {
      if (doc.lines) {
        files[path] = doc.lines.join('\n')
      }
    }
    return files
  } catch (err) {
    logger.error({ err, projectId }, 'Failed to get project files')
    return {}
  }
}

function _proxyJSON(path, options = {}) {
  const url = `${RESEARCHKIT_URL}${path}`
  const fetchOptions = {
    method: options.method || 'GET',
    headers: { 'Content-Type': 'application/json' },
  }
  if (options.body) {
    fetchOptions.body = JSON.stringify(options.body)
  }
  return fetch(url, fetchOptions)
}

const ResearchKitController = {
  async chat(req, res) {
    const { project_id } = req.params
    const {
      message,
      conversation_id,
      selected_text,
      file_path,
      selection_from,
      selection_to,
      cursor_line,
      line_from,
      line_to,
      config,
      current_file_content,
    } = req.body

    try {
      const files = await _getProjectFiles(project_id)

      // Override server-fetched files with client-provided content for the
      // active file. This ensures manual edits that haven't been flushed to
      // the document updater yet are still visible to the agent.
      if (current_file_content && typeof current_file_content === 'object') {
        for (const [path, content] of Object.entries(current_file_content)) {
          if (typeof content === 'string') {
            files[path] = content
          }
        }
      }

      const payload = JSON.stringify({
        project_id,
        message,
        conversation_id: conversation_id || null,
        selected_text: selected_text || null,
        file_path: file_path || null,
        selection_from: selection_from ?? null,
        selection_to: selection_to ?? null,
        cursor_line: cursor_line ?? null,
        line_from: line_from ?? null,
        line_to: line_to ?? null,
        files,
        config: config || null,
      })

      // Use http.request for reliable SSE streaming (fetch + getReader is unreliable in Node.js)
      const proxyReq = http.request(
        {
          hostname: parsedUrl.hostname,
          port: parsedUrl.port || 3020,
          path: '/api/chat',
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Content-Length': Buffer.byteLength(payload),
          },
        },
        proxyRes => {
          if (proxyRes.statusCode !== 200) {
            let body = ''
            proxyRes.on('data', chunk => {
              body += chunk
            })
            proxyRes.on('end', () => {
              logger.error(
                { project_id, status: proxyRes.statusCode, body },
                'ResearchKit chat error'
              )
              res.status(proxyRes.statusCode).json({ error: body })
            })
            return
          }

          // Set SSE headers and pipe the stream directly
          res.writeHead(200, {
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            Connection: 'keep-alive',
            'X-Accel-Buffering': 'no',
          })

          // Pipe Node.js stream directly — no buffering
          proxyRes.pipe(res)
        }
      )

      proxyReq.on('error', err => {
        logger.error({ err, project_id }, 'ResearchKit chat failed')
        if (!res.headersSent) {
          res.status(502).json({ error: 'ResearchKit service unavailable' })
        }
      })

      proxyReq.write(payload)
      proxyReq.end()
    } catch (err) {
      logger.error({ err, project_id }, 'ResearchKit chat failed')
      if (!res.headersSent) {
        res.status(500).json({ error: 'ResearchKit service unavailable' })
      }
    }
  },

  async indexProject(req, res) {
    const { project_id } = req.params

    try {
      const files = await _getProjectFiles(project_id)

      const response = await _proxyJSON('/api/project/index', {
        method: 'POST',
        body: { project_id, files },
      })

      const data = await response.json()
      res.status(response.status).json(data)
    } catch (err) {
      logger.error({ err, project_id }, 'ResearchKit index failed')
      res.status(500).json({ error: 'ResearchKit service unavailable' })
    }
  },

  async getMemory(req, res) {
    const { project_id } = req.params

    try {
      const response = await _proxyJSON(`/api/memory/${project_id}`)
      const data = await response.json()
      res.status(response.status).json(data)
    } catch (err) {
      logger.error({ err, project_id }, 'ResearchKit get memory failed')
      res.status(500).json({ error: 'ResearchKit service unavailable' })
    }
  },

  async getConversation(req, res) {
    const { project_id } = req.params
    const conversationId =
      typeof req.query.conversation_id === 'string'
        ? req.query.conversation_id
        : null
    const query = conversationId
      ? `?conversation_id=${encodeURIComponent(conversationId)}`
      : ''

    try {
      const response = await _proxyJSON(`/api/conversation/${project_id}${query}`)
      const data = await response.json()
      res.status(response.status).json(data)
    } catch (err) {
      logger.error({ err, project_id }, 'ResearchKit get conversation failed')
      res.status(500).json({ error: 'ResearchKit service unavailable' })
    }
  },

  async listConversations(req, res) {
    const { project_id } = req.params

    try {
      const response = await _proxyJSON(`/api/conversation/${project_id}/list`)
      const data = await response.json()
      res.status(response.status).json(data)
    } catch (err) {
      logger.error({ err, project_id }, 'ResearchKit list conversations failed')
      res.status(500).json({ error: 'ResearchKit service unavailable' })
    }
  },

  async getConfig(req, res) {
    const { project_id } = req.params

    try {
      const response = await _proxyJSON(`/api/config/${project_id}`)
      const data = await response.json()
      res.status(response.status).json(data)
    } catch (err) {
      logger.error({ err, project_id }, 'ResearchKit get config failed')
      res.status(500).json({ error: 'ResearchKit service unavailable' })
    }
  },

  async updateConfig(req, res) {
    const { project_id } = req.params

    try {
      const response = await _proxyJSON(`/api/config/${project_id}`, {
        method: 'POST',
        body: req.body,
      })
      const data = await response.json()
      res.status(response.status).json(data)
    } catch (err) {
      logger.error({ err, project_id }, 'ResearchKit update config failed')
      res.status(500).json({ error: 'ResearchKit service unavailable' })
    }
  },

  async testConfig(req, res) {
    const { project_id } = req.params

    try {
      const response = await _proxyJSON(`/api/config/${project_id}/test`, {
        method: 'POST',
        body: req.body || {},
      })
      const data = await response.json()
      res.status(response.status).json(data)
    } catch (err) {
      logger.error({ err, project_id }, 'ResearchKit test config failed')
      res.status(500).json({ error: 'ResearchKit service unavailable' })
    }
  },

  async listModels(req, res) {
    const { project_id } = req.params

    try {
      const response = await _proxyJSON(`/api/models/${project_id}`, {
        method: 'POST',
        body: req.body || {},
      })
      const data = await response.json()
      res.status(response.status).json(data)
    } catch (err) {
      logger.error({ err, project_id }, 'ResearchKit list models failed')
      res.status(500).json({ error: 'ResearchKit service unavailable' })
    }
  },

  async clearConversation(req, res) {
    const { project_id } = req.params
    const conversationId =
      typeof req.query.conversation_id === 'string'
        ? req.query.conversation_id
        : null
    const query = conversationId
      ? `?conversation_id=${encodeURIComponent(conversationId)}`
      : ''

    try {
      const response = await _proxyJSON(
        `/api/conversation/${project_id}${query}`,
        { method: 'DELETE' }
      )
      const data = await response.json()
      res.status(response.status).json(data)
    } catch (err) {
      logger.error(
        { err, project_id },
        'ResearchKit clear conversation failed'
      )
      res.status(500).json({ error: 'Failed to clear conversation' })
    }
  },
}

export default ResearchKitController
