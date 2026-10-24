// Explicit route patterns keep record identifiers and URL parameters out of the page title.
export type LocalizedTitle = { readonly en: string; readonly fr: string };

export function routeTitleText(
  title: LocalizedTitle | undefined,
  language: string,
  i18nEnabled: boolean
): string {
  if (!title) return 'Page';
  if (i18nEnabled && language.toLowerCase().startsWith('fr')) return title.fr;
  return title.en;
}

export const routeTitles: ReadonlyArray<readonly [string, LocalizedTitle]> = [
  ['/', { en: 'Dashboard', fr: 'Tableau de bord' }],
  ['/unauthorized', { en: 'Unauthorized', fr: 'Non autorisé' }],
  ['/profile', { en: 'Profile', fr: 'Profil' }],
  ['/chat-settings', { en: 'Chat Settings', fr: 'Paramètres du chat' }],
  ['/governance', { en: 'Governance', fr: 'Gouvernance' }],
  ['/onboarding', { en: 'Onboarding', fr: 'Prise en main' }],
  ['/workspace', { en: 'Workspace', fr: 'Espace de travail' }],
  ['/discover', { en: 'Discover', fr: 'Découvrir' }],
  ['/marketplace', { en: 'Marketplace', fr: 'Place de marché' }],
  ['/services', { en: 'Services', fr: 'Services' }],
  ['/servers', { en: 'Servers', fr: 'Serveurs' }],
  ['/servers/:serverId', { en: 'Servers Details', fr: 'Détails des serveurs' }],
  ['/tools', { en: 'Tools', fr: 'Outils' }],
  ['/tools/:id', { en: 'Tools Details', fr: 'Détails des outils' }],
  ['/subscriptions', { en: 'Subscriptions', fr: 'Abonnements' }],
  ['/apis', { en: 'APIs', fr: 'APIs' }],
  ['/apis/:id', { en: 'API Details', fr: "Détails de l'API" }],
  ['/apis/:id/test', { en: 'API Testing Sandbox', fr: "Bac à sable de test d'API" }],
  ['/apps', { en: 'Apps', fr: 'Applications' }],
  ['/apps/:id', { en: 'Apps Details', fr: 'Détails des applications' }],
  ['/contracts', { en: 'Contracts', fr: 'Contrats' }],
  ['/usage', { en: 'Usage', fr: 'Utilisation' }],
  ['/executions', { en: 'Executions', fr: 'Exécutions' }],
  ['/service-accounts', { en: 'Service Accounts', fr: 'Comptes de service' }],
  ['/notifications', { en: 'Notifications', fr: 'Notifications' }],
  ['/audit-log', { en: 'Audit Log', fr: "Journal d'audit" }],
  ['/favorites', { en: 'Favorites', fr: 'Favoris' }],
  ['/rate-limits', { en: 'Rate Limits', fr: 'Limites de débit' }],
  ['/api-compare', { en: 'API Compare', fr: "Comparaison d'API" }],
  ['/my-servers', { en: 'My Servers', fr: 'Mes serveurs' }],
  ['/my-apis', { en: 'My APIs', fr: 'Mes APIs' }],
  ['/contracts/new', { en: 'Contracts / New', fr: 'Contrats / Nouveau' }],
  ['/contracts/:id', { en: 'Contracts Details', fr: 'Détails des contrats' }],
  ['/consumers/register', { en: 'Consumers / Register', fr: 'Consommateurs / Inscription' }],
  ['/gateways', { en: 'Gateways', fr: 'Passerelles' }],
  ['/credentials', { en: 'Credentials', fr: 'Identifiants' }],
  ['/webhooks', { en: 'Webhooks', fr: 'Webhooks' }],
  ['/signup', { en: 'Signup', fr: 'Inscription' }],
];
