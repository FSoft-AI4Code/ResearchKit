import ResearchKitController from './ResearchKitController.mjs'
import AuthorizationMiddleware from '../../../../app/src/Features/Authorization/AuthorizationMiddleware.mjs'

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

    // Get current conversation history
    webRouter.get(
      '/project/:project_id/researchkit/conversation',
      AuthorizationMiddleware.ensureUserCanReadProject,
      ResearchKitController.getConversation
    )
    webRouter.get(
      '/project/:project_id/researchkit/conversations',
      AuthorizationMiddleware.ensureUserCanReadProject,
      ResearchKitController.listConversations
    )

    // Get/update config
    webRouter.get(
      '/project/:project_id/researchkit/config',
      AuthorizationMiddleware.ensureUserCanReadProject,
      ResearchKitController.getConfig
    )
    webRouter.post(
      '/project/:project_id/researchkit/config',
      AuthorizationMiddleware.ensureUserCanWriteProjectSettings,
      ResearchKitController.updateConfig
    )
    webRouter.post(
      '/project/:project_id/researchkit/config/test',
      AuthorizationMiddleware.ensureUserCanReadProject,
      ResearchKitController.testConfig
    )

    // Fetch available models for the current provider configuration
    webRouter.post(
      '/project/:project_id/researchkit/models',
      AuthorizationMiddleware.ensureUserCanReadProject,
      ResearchKitController.listModels
    )

    // Clear conversation history
    webRouter.delete(
      '/project/:project_id/researchkit/conversation',
      AuthorizationMiddleware.ensureUserCanReadProject,
      ResearchKitController.clearConversation
    )
  },
}
