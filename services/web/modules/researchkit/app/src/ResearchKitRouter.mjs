import ResearchKitController from './ResearchKitController.mjs'
import AuthorizationMiddleware from '../../../../app/src/Features/Authorization/AuthorizationMiddleware.mjs'
import AuthenticationController from '../../../../app/src/Features/Authentication/AuthenticationController.mjs'

export default {
  apply(webRouter) {
    // Chat with the Main Agent (proxied to Python service, returns SSE stream)
    webRouter.post(
      '/project/:project_id/researchkit/chat',
      AuthorizationMiddleware.ensureUserCanReadProject,
      ResearchKitController.chat
    )

    // Index project to build Memory
    webRouter.post(
      '/project/:project_id/researchkit/index',
      AuthorizationMiddleware.ensureUserCanReadProject,
      ResearchKitController.indexProject
    )

    // Get Memory state
    webRouter.get(
      '/project/:project_id/researchkit/memory',
      AuthorizationMiddleware.ensureUserCanReadProject,
      ResearchKitController.getMemory
    )

    // Get/update config
    webRouter.get(
      '/project/:project_id/researchkit/config',
      AuthorizationMiddleware.ensureUserCanReadProject,
      ResearchKitController.getConfig
    )
    webRouter.post(
      '/project/:project_id/researchkit/config',
      AuthorizationMiddleware.ensureUserCanReadProject,
      ResearchKitController.updateConfig
    )

    // Clear conversation history
    webRouter.delete(
      '/project/:project_id/researchkit/conversation',
      AuthorizationMiddleware.ensureUserCanReadProject,
      ResearchKitController.clearConversation
    )
  },
}
