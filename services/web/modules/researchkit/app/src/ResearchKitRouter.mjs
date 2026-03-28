import logger from '@overleaf/logger'
import AuthorizationMiddleware from '../../../../app/src/Features/Authorization/AuthorizationMiddleware.mjs'
import SessionManager from '../../../../app/src/Features/Authentication/SessionManager.mjs'

const RESEARCHKIT_URL = process.env.RESEARCHKIT_URL || 'http://researchkit:3020'

export default {
  apply(webRouter) {
    logger.debug({}, 'Init ResearchKit router')

    webRouter.post(
      '/project/:project_id/researchkit/chat',
      AuthorizationMiddleware.ensureUserCanReadProject,
      async (req, res) => {
        const { project_id: projectId } = req.params
        const userId = SessionManager.getLoggedInUserId(req.session)
        try {
          const response = await fetch(`${RESEARCHKIT_URL}/api/chat`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              project_id: projectId,
              user_id: userId,
              ...req.body,
            }),
          })
          res.status(response.status)
          if (response.headers.get('content-type')?.includes('text/event-stream')) {
            res.setHeader('Content-Type', 'text/event-stream')
            res.setHeader('Cache-Control', 'no-cache')
            res.setHeader('Connection', 'keep-alive')
            const reader = response.body.getReader()
            const pump = async () => {
              const { done, value } = await reader.read()
              if (done) {
                res.end()
                return
              }
              res.write(value)
              await pump()
            }
            await pump()
          } else {
            const data = await response.json()
            res.json(data)
          }
        } catch (err) {
          logger.error({ err, projectId }, 'ResearchKit chat proxy error')
          res.status(502).json({ error: 'ResearchKit service unavailable' })
        }
      }
    )

    webRouter.post(
      '/project/:project_id/researchkit/index',
      AuthorizationMiddleware.ensureUserCanReadProject,
      async (req, res) => {
        const { project_id: projectId } = req.params
        try {
          const response = await fetch(`${RESEARCHKIT_URL}/api/project/index`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ project_id: projectId, ...req.body }),
          })
          const data = await response.json()
          res.status(response.status).json(data)
        } catch (err) {
          logger.error({ err, projectId }, 'ResearchKit index proxy error')
          res.status(502).json({ error: 'ResearchKit service unavailable' })
        }
      }
    )

    webRouter.get(
      '/project/:project_id/researchkit/memory',
      AuthorizationMiddleware.ensureUserCanReadProject,
      async (req, res) => {
        const { project_id: projectId } = req.params
        try {
          const response = await fetch(
            `${RESEARCHKIT_URL}/api/memory?project_id=${projectId}`
          )
          const data = await response.json()
          res.status(response.status).json(data)
        } catch (err) {
          logger.error({ err, projectId }, 'ResearchKit memory proxy error')
          res.status(502).json({ error: 'ResearchKit service unavailable' })
        }
      }
    )
  },
}
