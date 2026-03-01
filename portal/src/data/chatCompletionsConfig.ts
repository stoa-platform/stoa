/**
 * Static enrichment config for the "IA — Chat Completions (GPT-4o)" API.
 * Rendered by ChatCompletionsEnrichment when the current API matches.
 */

export const CHAT_COMPLETIONS_API_NAME = 'IA — Chat Completions (GPT-4o)';

export const CHAT_COMPLETIONS_TAGS = ['ia', 'llm', 'azure-openai', 'self-service'] as const;

export const CHAT_COMPLETIONS_OWNER = 'Equipe Data & IA';

export interface SubscriptionPlan {
  name: string;
  slug: string;
  namespace: string;
  tokensPerMinute: number;
  requestsPerMinute: number;
  description: string;
}

export const PLANS: SubscriptionPlan[] = [
  {
    name: 'Projet Alpha — Exploration',
    slug: 'alpha-exploration',
    namespace: 'alpha',
    tokensPerMinute: 1_000,
    requestsPerMinute: 10,
    description: 'Ideal pour le prototypage et les premiers tests d\u2019integration.',
  },
  {
    name: 'Projet Beta — Production',
    slug: 'beta-production',
    namespace: 'beta',
    tokensPerMinute: 5_000,
    requestsPerMinute: 50,
    description: 'Pour les workloads de production avec des quotas eleves.',
  },
];

export const CURL_EXAMPLE = `curl -X POST \\
  \${STOA_GATEWAY_URL}/v1/chat/completions \\
  -H "Authorization: Bearer $API_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "model": "gpt-4o",
    "messages": [
      {"role": "system", "content": "You are a helpful assistant."},
      {"role": "user", "content": "Explain API gateways in one sentence."}
    ],
    "stream": true
  }'`;

export const CURL_RESPONSE = `{
  "id": "chatcmpl-abc123",
  "object": "chat.completion",
  "created": 1709000000,
  "model": "gpt-4o",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "An API gateway is a server that acts as a single entry point..."
      },
      "finish_reason": "stop"
    }
  ],
  "usage": {
    "prompt_tokens": 25,
    "completion_tokens": 18,
    "total_tokens": 43
  }
}`;

export const GDPR_NOTICE =
  'Les donnees envoyees a cette API sont traitees par Azure OpenAI (region Europe). ' +
  'Aucune donnee n\u2019est utilisee pour l\u2019entrainement des modeles. ' +
  'Consultez votre DPO avant d\u2019envoyer des donnees personnelles ou sensibles.';

export const API_KEY_NOTICE =
  'Les cles API Azure OpenAI sont gerees de maniere centralisee par l\u2019equipe plateforme. ' +
  'Votre souscription vous fournit une cle STOA dediee qui est routee vers Azure en backend.';
