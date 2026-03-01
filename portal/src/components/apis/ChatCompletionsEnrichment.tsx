import { AlertTriangle, Shield, Zap } from 'lucide-react';
import {
  CHAT_COMPLETIONS_API_NAME,
  CURL_EXAMPLE,
  CURL_RESPONSE,
  GDPR_NOTICE,
  API_KEY_NOTICE,
  PLANS,
} from '../../data/chatCompletionsConfig';

interface ChatCompletionsEnrichmentProps {
  apiName: string;
}

/**
 * Enrichment panel rendered on the API detail page when the current API
 * matches the Chat Completions API name.
 */
export function ChatCompletionsEnrichment({ apiName }: ChatCompletionsEnrichmentProps) {
  if (apiName !== CHAT_COMPLETIONS_API_NAME) {
    return null;
  }

  return (
    <div className="space-y-6" data-testid="chat-completions-enrichment">
      {/* SSE Streaming badge */}
      <div className="flex items-center gap-2">
        <span className="inline-flex items-center gap-1 rounded-full bg-green-100 px-3 py-1 text-sm font-medium text-green-800 dark:bg-green-900 dark:text-green-200">
          <Zap className="h-4 w-4" />
          SSE Streaming
        </span>
      </div>

      {/* Curl example */}
      <section>
        <h3 className="mb-2 text-lg font-semibold text-neutral-900 dark:text-white">
          Exemple de requete
        </h3>
        <pre className="overflow-x-auto rounded-lg bg-neutral-900 p-4 text-sm text-green-400">
          <code>{CURL_EXAMPLE}</code>
        </pre>
      </section>

      {/* Response example */}
      <section>
        <h3 className="mb-2 text-lg font-semibold text-neutral-900 dark:text-white">
          Exemple de reponse
        </h3>
        <pre className="overflow-x-auto rounded-lg bg-neutral-900 p-4 text-sm text-green-400">
          <code>{CURL_RESPONSE}</code>
        </pre>
      </section>

      {/* Subscription plans */}
      <section>
        <h3 className="mb-3 text-lg font-semibold text-neutral-900 dark:text-white">
          Plans de souscription
        </h3>
        <div className="grid gap-4 md:grid-cols-2">
          {PLANS.map((plan) => (
            <div
              key={plan.slug}
              className="rounded-lg border border-neutral-200 p-4 dark:border-neutral-700"
            >
              <h4 className="font-semibold text-neutral-900 dark:text-white">{plan.name}</h4>
              <p className="mt-1 text-sm text-neutral-600 dark:text-neutral-400">
                {plan.description}
              </p>
              <ul className="mt-3 space-y-1 text-sm text-neutral-700 dark:text-neutral-300">
                <li>
                  <strong>{plan.tokensPerMinute.toLocaleString()}</strong> tokens/min
                </li>
                <li>
                  <strong>{plan.requestsPerMinute}</strong> req/min
                </li>
                <li>
                  Namespace: <code className="text-xs">{plan.namespace}</code>
                </li>
              </ul>
            </div>
          ))}
        </div>
      </section>

      {/* GDPR notice */}
      <div
        className="flex gap-3 rounded-lg border border-amber-300 bg-amber-50 p-4 dark:border-amber-700 dark:bg-amber-950"
        role="alert"
      >
        <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0 text-amber-600 dark:text-amber-400" />
        <p className="text-sm text-amber-800 dark:text-amber-200">{GDPR_NOTICE}</p>
      </div>

      {/* API key notice */}
      <div className="flex gap-3 rounded-lg border border-blue-300 bg-blue-50 p-4 dark:border-blue-700 dark:bg-blue-950">
        <Shield className="mt-0.5 h-5 w-5 shrink-0 text-blue-600 dark:text-blue-400" />
        <p className="text-sm text-blue-800 dark:text-blue-200">{API_KEY_NOTICE}</p>
      </div>
    </div>
  );
}
