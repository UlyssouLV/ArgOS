import {themes as prismThemes} from 'prism-react-renderer';
import type {Config} from '@docusaurus/types';
import type * as Preset from '@docusaurus/preset-classic';

// Placeholders remplacés par scaffold-docs-site.sh : __OWNER__ __REPO__ __TITLE__ __TAGLINE__
const OWNER = '__OWNER__';
const REPO = '__REPO__';
const TITLE = '__TITLE__';
const TAGLINE = '__TAGLINE__';

const config: Config = {
  title: TITLE,
  tagline: TAGLINE,
  url: `https://${OWNER}.github.io`,
  baseUrl: `/${REPO}/`,

  organizationName: OWNER,
  projectName: REPO,

  onBrokenLinks: 'warn',
  markdown: {
    hooks: {
      onBrokenMarkdownLinks: 'warn',
    },
  },

  i18n: {
    defaultLocale: 'fr',
    locales: ['fr'],
  },

  presets: [
    [
      'classic',
      {
        docs: {
          path: '../docs',
          routeBasePath: 'docs',
          sidebarPath: './sidebars.ts',
          numberPrefixParser: false,
          exclude: [
            'suivi-avancement/**',
            'specs/**',
            'dev/**',
            'img/**',
            'changelog/README.md',
            'feuille-de-route/README.md',
            'bugs/README.md',
          ],
        },
        blog: false,
        theme: {
          customCss: './src/css/custom.css',
        },
      } satisfies Preset.Options,
    ],
  ],

  themeConfig: {
    colorMode: {
      defaultMode: 'light',
      disableSwitch: true,
      respectPrefersColorScheme: false,
    },
    navbar: {
      title: TITLE,
      items: [
        {
          to: '/',
          label: 'Accueil',
          position: 'left',
        },
        {
          type: 'docSidebar',
          sidebarId: 'featuresSidebar',
          position: 'left',
          label: 'Features',
        },
        {
          type: 'docSidebar',
          sidebarId: 'changelogSidebar',
          position: 'left',
          label: 'Changelog',
        },
        {
          type: 'docSidebar',
          sidebarId: 'bugsSidebar',
          position: 'left',
          label: 'Bugs',
        },
        {
          type: 'docSidebar',
          sidebarId: 'adrSidebar',
          position: 'left',
          label: 'ADR',
        },
        {
          type: 'doc',
          docId: 'glossaire',
          position: 'left',
          label: 'Glossaire',
        },
        {
          href: `https://github.com/${OWNER}/${REPO}`,
          label: 'GitHub',
          position: 'right',
        },
      ],
    },
    footer: {
      style: 'light',
      copyright: `${TITLE} — documentation.`,
    },
    prism: {
      theme: prismThemes.github,
      darkTheme: prismThemes.dracula,
    },
  } satisfies Preset.ThemeConfig,
};

export default config;
