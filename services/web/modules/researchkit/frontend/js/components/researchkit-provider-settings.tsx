import { ChangeEvent, FC, useCallback, useEffect, useMemo, useState } from 'react'
import { getJSON, postJSON } from '@/infrastructure/fetch-json'
import { useProjectContext } from '@/shared/context/project-context'

type RKConfigResponse = {
  provider_type: string
  base_url: string | null
  model: string
  workspace_path: string | null
  runner_url: string | null
  bash_default_timeout_seconds: number
  max_tool_iterations: number
  tool_output_max_chars: number
  has_api_key: boolean
  has_asta_api_key: boolean
}

type RKModelOption = {
  id: string
  label: string
}

type RKModelListResponse = {
  provider_type: string
  models: RKModelOption[]
  selected_model: string | null
}

type RKConfigTestResponse = {
  success: boolean
  provider_type: string
  model: string
  latency_ms: number
  message: string
  response_preview: string | null
}

function extractErrorMessage(error: unknown, fallback: string): string {
  if (typeof error === 'object' && error !== null) {
    const withData = error as { data?: { detail?: unknown } }
    if (typeof withData.data?.detail === 'string' && withData.data.detail.trim()) {
      return withData.data.detail
    }
  }
  if (error instanceof Error && error.message) {
    return error.message
  }
  return fallback
}

const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI' },
  { value: 'anthropic', label: 'Anthropic' },
  { value: 'custom', label: 'Custom (OpenAI-compatible)' },
]

function normalizeConfig(config: RKConfigResponse): RKConfigResponse {
  return {
    provider_type: config.provider_type || 'openai',
    base_url: config.base_url || null,
    model: config.model || '',
    workspace_path: config.workspace_path || null,
    runner_url: config.runner_url || null,
    bash_default_timeout_seconds: Number.isFinite(
      config.bash_default_timeout_seconds
    )
      ? config.bash_default_timeout_seconds
      : 60,
    max_tool_iterations: Number.isFinite(config.max_tool_iterations)
      ? config.max_tool_iterations
      : 8,
    tool_output_max_chars: Number.isFinite(config.tool_output_max_chars)
      ? config.tool_output_max_chars
      : 12000,
    has_api_key: Boolean(config.has_api_key),
    has_asta_api_key: Boolean(config.has_asta_api_key),
  }
}

export const ResearchKitProviderSettings: FC = () => {
  const { projectId } = useProjectContext()
  const [config, setConfig] = useState<RKConfigResponse | null>(null)
  const [apiKeyInput, setApiKeyInput] = useState('')
  const [clearApiKey, setClearApiKey] = useState(false)
  const [astaApiKeyInput, setAstaApiKeyInput] = useState('')
  const [clearAstaApiKey, setClearAstaApiKey] = useState(false)
  const [modelOptions, setModelOptions] = useState<RKModelOption[]>([])
  const [isLoadingConfig, setIsLoadingConfig] = useState(true)
  const [isFetchingModels, setIsFetchingModels] = useState(false)
  const [isSaving, setIsSaving] = useState(false)
  const [isTesting, setIsTesting] = useState(false)
  const [configError, setConfigError] = useState<string | null>(null)
  const [modelError, setModelError] = useState<string | null>(null)
  const [saveMessage, setSaveMessage] = useState<string | null>(null)
  const [testMessage, setTestMessage] = useState<string | null>(null)
  const [testError, setTestError] = useState<string | null>(null)

  const hasSavedApiKey = Boolean(config?.has_api_key)
  const hasSavedAstaApiKey = Boolean(config?.has_asta_api_key)
  const providerType = config?.provider_type || 'openai'
  const baseUrl = config?.base_url || ''
  const model = config?.model || ''
  const hasListedModel = useMemo(
    () => modelOptions.some(option => option.id === model),
    [modelOptions, model]
  )

  useEffect(() => {
    let cancelled = false
    setIsLoadingConfig(true)
    setConfigError(null)
    setSaveMessage(null)
    setTestMessage(null)
    setTestError(null)
    setApiKeyInput('')
    setClearApiKey(false)
    setAstaApiKeyInput('')
    setClearAstaApiKey(false)
    setModelOptions([])

    getJSON<RKConfigResponse>(`/project/${projectId}/researchkit/config`)
      .then(data => {
        if (cancelled) return
        setConfig(normalizeConfig(data))
      })
      .catch(err => {
        if (cancelled) return
        setConfigError(
          err instanceof Error ? err.message : 'Failed to load provider settings.'
        )
      })
      .finally(() => {
        if (!cancelled) {
          setIsLoadingConfig(false)
        }
      })

    return () => {
      cancelled = true
    }
  }, [projectId])

  const fetchModels = useCallback(
    async (draftConfig: RKConfigResponse, draftApiKey: string) => {
      setIsFetchingModels(true)
      setModelError(null)
      try {
        const requestBody: Record<string, unknown> = {
          provider_type: draftConfig.provider_type,
          base_url: draftConfig.base_url,
        }
        const trimmedApiKey = draftApiKey.trim()
        if (trimmedApiKey) {
          requestBody.api_key = trimmedApiKey
        }

        const data = await postJSON<RKModelListResponse>(
          `/project/${projectId}/researchkit/models`,
          { body: requestBody }
        )

        const models = Array.isArray(data.models) ? data.models : []
        setModelOptions(models)
        if (!draftConfig.model && data.selected_model) {
          setConfig(prev =>
            prev ? { ...prev, model: data.selected_model || prev.model } : prev
          )
        }
      } catch (err) {
        setModelOptions([])
        setModelError(extractErrorMessage(
          err,
          'Failed to fetch models. You can still enter a model manually.'
        ))
      } finally {
        setIsFetchingModels(false)
      }
    },
    [projectId]
  )

  useEffect(() => {
    if (!config) {
      return
    }
    const discoveryConfig = config
    const timeout = window.setTimeout(() => {
      void fetchModels(discoveryConfig, apiKeyInput)
    }, 400)
    return () => {
      window.clearTimeout(timeout)
    }
  }, [config?.provider_type, config?.base_url, apiKeyInput, fetchModels])

  const handleProviderChange = useCallback((event: ChangeEvent<HTMLSelectElement>) => {
    const nextProvider = event.target.value
    setConfig(prev => (prev ? { ...prev, provider_type: nextProvider } : prev))
    setSaveMessage(null)
  }, [])

  const handleBaseUrlChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const nextBaseUrl = event.target.value.trim()
    setConfig(prev => (prev ? { ...prev, base_url: nextBaseUrl || null } : prev))
    setSaveMessage(null)
  }, [])

  const handleModelSelectChange = useCallback(
    (event: ChangeEvent<HTMLSelectElement>) => {
      const nextModel = event.target.value.trim()
      setConfig(prev => (prev ? { ...prev, model: nextModel } : prev))
      setSaveMessage(null)
    },
    []
  )

  const handleModelInputChange = useCallback((event: ChangeEvent<HTMLInputElement>) => {
    const nextModel = event.target.value
    setConfig(prev => (prev ? { ...prev, model: nextModel } : prev))
    setSaveMessage(null)
  }, [])

  const refreshModels = useCallback(() => {
    if (!config) return
    void fetchModels(config, apiKeyInput)
  }, [config, apiKeyInput, fetchModels])

  const saveConfig = useCallback(async () => {
    if (!config) return
    setIsSaving(true)
    setConfigError(null)
    setSaveMessage(null)
    setTestMessage(null)
    setTestError(null)

    const trimmedModel = config.model.trim()
    if (!trimmedModel) {
      setConfigError('Model is required.')
      setIsSaving(false)
      return
    }

    const trimmedApiKey = apiKeyInput.trim()
    const shouldClear = clearApiKey && !trimmedApiKey
    const trimmedAstaApiKey = astaApiKeyInput.trim()
    const shouldClearAstaApiKey = clearAstaApiKey && !trimmedAstaApiKey
    try {
      await postJSON(`/project/${projectId}/researchkit/config`, {
        body: {
          provider_type: config.provider_type,
          base_url: config.base_url,
          model: trimmedModel,
          workspace_path: config.workspace_path,
          runner_url: config.runner_url,
          bash_default_timeout_seconds: config.bash_default_timeout_seconds,
          max_tool_iterations: config.max_tool_iterations,
          tool_output_max_chars: config.tool_output_max_chars,
          api_key: trimmedApiKey || undefined,
          clear_api_key: shouldClear,
          asta_api_key: trimmedAstaApiKey || undefined,
          clear_asta_api_key: shouldClearAstaApiKey,
        },
      })

      setConfig(prev =>
        prev
          ? {
              ...prev,
              model: trimmedModel,
              has_api_key: trimmedApiKey ? true : shouldClear ? false : prev.has_api_key,
              has_asta_api_key: trimmedAstaApiKey
                ? true
                : shouldClearAstaApiKey
                  ? false
                  : prev.has_asta_api_key,
            }
          : prev
      )
      if (trimmedApiKey || shouldClear || trimmedAstaApiKey || shouldClearAstaApiKey) {
        setApiKeyInput('')
        setAstaApiKeyInput('')
      }
      if (shouldClear) {
        setClearApiKey(false)
      }
      if (shouldClearAstaApiKey) {
        setClearAstaApiKey(false)
      }
      setSaveMessage('Provider settings saved.')
    } catch (err) {
      setConfigError(extractErrorMessage(err, 'Failed to save provider settings.'))
    } finally {
      setIsSaving(false)
    }
  }, [
    apiKeyInput,
    astaApiKeyInput,
    clearAstaApiKey,
    clearApiKey,
    config,
    projectId,
  ])

  const testConfig = useCallback(async () => {
    if (!config) return
    setIsTesting(true)
    setConfigError(null)
    setTestMessage(null)
    setTestError(null)
    setSaveMessage(null)

    const trimmedModel = config.model.trim()
    if (!trimmedModel) {
      setTestError('Model is required for test.')
      setIsTesting(false)
      return
    }

    try {
      const trimmedApiKey = apiKeyInput.trim()
      const data = await postJSON<RKConfigTestResponse>(
        `/project/${projectId}/researchkit/config/test`,
        {
          body: {
            provider_type: config.provider_type,
            base_url: config.base_url,
            model: trimmedModel,
            api_key: trimmedApiKey || undefined,
          },
        }
      )

      const latencyPart =
        Number.isFinite(data.latency_ms) && data.latency_ms >= 0
          ? ` (${data.latency_ms} ms)`
          : ''
      const previewPart = data.response_preview
        ? ` Response: ${data.response_preview}`
        : ''
      setTestMessage(`${data.message}${latencyPart}.${previewPart}`)
    } catch (err) {
      setTestError(extractErrorMessage(err, 'Provider configuration test failed.'))
    } finally {
      setIsTesting(false)
    }
  }, [apiKeyInput, config, projectId])

  return (
    <details className="rk-settings">
      <summary className="rk-settings-summary">Provider Settings</summary>
      <div className="rk-settings-body">
        {isLoadingConfig && <div className="rk-settings-info">Loading settings...</div>}
        {config && (
          <>
            <div className="rk-settings-row">
              <label className="rk-settings-label" htmlFor="rk-provider-select">
                Provider
              </label>
              <select
                id="rk-provider-select"
                className="rk-settings-select"
                value={providerType}
                onChange={handleProviderChange}
                disabled={isSaving}
              >
                {PROVIDER_OPTIONS.map(option => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            </div>

            <div className="rk-settings-row">
              <label className="rk-settings-label" htmlFor="rk-base-url-input">
                Base URL
              </label>
              <input
                id="rk-base-url-input"
                className="rk-settings-input"
                type="text"
                placeholder={
                  providerType === 'anthropic'
                    ? 'Optional (default Anthropic API)'
                    : providerType === 'custom'
                      ? 'Required for custom provider'
                      : 'Optional (default OpenAI API)'
                }
                value={baseUrl}
                onChange={handleBaseUrlChange}
                disabled={isSaving}
              />
            </div>

            <div className="rk-settings-row">
              <label className="rk-settings-label" htmlFor="rk-api-key-input">
                API Key
              </label>
              <input
                id="rk-api-key-input"
                className="rk-settings-input"
                type="password"
                placeholder={hasSavedApiKey ? 'Saved key present' : 'Enter API key'}
                value={apiKeyInput}
                onChange={event => {
                  setApiKeyInput(event.target.value)
                  setSaveMessage(null)
                }}
                disabled={isSaving}
              />
              {hasSavedApiKey && (
                <label className="rk-settings-checkbox">
                  <input
                    type="checkbox"
                    checked={clearApiKey}
                    onChange={event => {
                      setClearApiKey(event.target.checked)
                      setSaveMessage(null)
                    }}
                    disabled={isSaving || Boolean(apiKeyInput.trim())}
                  />
                  Clear saved key on save
                </label>
              )}
            </div>

            <div className="rk-settings-row">
              <label className="rk-settings-label" htmlFor="rk-asta-api-key-input">
                ASTA API Key
              </label>
              <input
                id="rk-asta-api-key-input"
                className="rk-settings-input"
                type="password"
                placeholder={
                  hasSavedAstaApiKey ? 'Saved key present' : 'Required for ASTA search'
                }
                value={astaApiKeyInput}
                onChange={event => {
                  setAstaApiKeyInput(event.target.value)
                  setSaveMessage(null)
                }}
                disabled={isSaving}
              />
              {hasSavedAstaApiKey && (
                <label className="rk-settings-checkbox">
                  <input
                    type="checkbox"
                    checked={clearAstaApiKey}
                    onChange={event => {
                      setClearAstaApiKey(event.target.checked)
                      setSaveMessage(null)
                    }}
                    disabled={isSaving || Boolean(astaApiKeyInput.trim())}
                  />
                  Clear saved key on save
                </label>
              )}
            </div>

            <div className="rk-settings-row">
              <div className="rk-settings-label-row">
                <label className="rk-settings-label" htmlFor="rk-model-select">
                  Model
                </label>
                <button
                  type="button"
                  className="rk-settings-secondary-btn"
                  onClick={refreshModels}
                  disabled={isSaving || isFetchingModels}
                >
                  {isFetchingModels ? 'Fetching...' : 'Refresh'}
                </button>
              </div>
              <select
                id="rk-model-select"
                className="rk-settings-select"
                value={hasListedModel ? model : ''}
                onChange={handleModelSelectChange}
                disabled={isSaving || isFetchingModels || modelOptions.length === 0}
              >
                <option value="">
                  {modelOptions.length > 0
                    ? 'Select discovered model'
                    : 'No discovered models'}
                </option>
                {modelOptions.map(option => (
                  <option key={option.id} value={option.id}>
                    {option.label}
                  </option>
                ))}
              </select>
              <input
                className="rk-settings-input"
                type="text"
                placeholder="Manual model name"
                value={model}
                onChange={handleModelInputChange}
                disabled={isSaving}
              />
            </div>

            <div className="rk-settings-actions">
              <button
                type="button"
                className="rk-settings-primary-btn"
                onClick={saveConfig}
                disabled={isSaving || isLoadingConfig || isTesting}
              >
                {isSaving ? 'Saving...' : 'Save'}
              </button>
              <button
                type="button"
                className="rk-settings-secondary-btn"
                onClick={testConfig}
                disabled={isSaving || isLoadingConfig || isTesting}
              >
                {isTesting ? 'Testing...' : 'Test'}
              </button>
              {saveMessage && <span className="rk-settings-success">{saveMessage}</span>}
            </div>
          </>
        )}
        {testMessage && <div className="rk-settings-success">{testMessage}</div>}
        {testError && <div className="rk-settings-error">{testError}</div>}
        {modelError && <div className="rk-settings-warning">{modelError}</div>}
        {configError && <div className="rk-settings-error">{configError}</div>}
      </div>
    </details>
  )
}
