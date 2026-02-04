import { themes as prismThemes } from 'prism-react-renderer';
import type { Config } from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

const config: Config = {
  title: 'STOA Platform',
  tagline: 'Multi-Tenant API Management for the AI Era',
  favicon: 'img/favicon.svg',

  url: 'https://docs.gostoa.dev',
  baseUrl: '/',

  organizationName: 'stoa-platform',
  projectName: 'stoa-docs',

  onBrokenLinks: 'throw',

  i18n: {
    defaultLocale: 'en',
    locales: ['en'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          sidebarPath: './sidebars.ts',
          routeBasePath: '/',
          editUrl: 'https://github.com/stoa-platform/stoa-docs/tree/main/',
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    image: 'img/logo.svg',
    navbar: {
      title: 'STOA',
      logo: {
        alt: 'STOA Logo',
        src: 'img/logo.svg',
      },
      items: [
        {
          type: 'docSidebar',
          sidebarId: 'docs',
          position: 'left',
          label: 'Documentation',
        },
        {
          href: 'https://portal.gostoa.dev',
          label: 'Portal',
          position: 'right',
        },
        {
          href: 'https://console.gostoa.dev',
          label: 'Console',
          position: 'right',
        },
        {
          href: 'https://github.com/stoa-platform/stoa',
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'dark',
      links: [
        {
          title: 'Documentation',
          items: [
            { label: 'Introduction', to: '/' },
            { label: 'Quickstart', to: '/getting-started/quickstart' },
            { label: 'Architecture', to: '/getting-started/architecture' },
          ],
        },
        {
          title: 'Platform',
          items: [
            { label: 'Developer Portal', href: 'https://portal.gostoa.dev' },
            { label: 'Console', href: 'https://console.gostoa.dev' },
            { label: 'API Gateway', href: 'https://apis.gostoa.dev' },
          ],
        },
        {
          title: 'More',
          items: [
            { label: 'GitHub', href: 'https://github.com/stoa-platform/stoa' },
            { label: 'Security', href: 'mailto:security@gostoa.dev' },
          ],
        },
      ],
      copyright: `Copyright \u00a9 ${new Date().getFullYear()} STOA Platform. All rights reserved.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
      additionalLanguages: ['bash', 'yaml', 'json', 'python', 'rust', 'toml'],
    },
    colorMode: {
      defaultMode: 'light',
      disableSwitch: false,
      respectPrefersColorScheme: true,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
