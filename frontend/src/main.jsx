import React from 'react';
import { createRoot } from 'react-dom/client';
import { Application, ApplicationHashRouter, I18nModule } from 'asab_webui_shell';

import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap-icons/font/bootstrap-icons.css';
import './styles.scss';

import TicketMasterModule from './ticketmaster/TicketMasterModule.jsx';

const ConfigDefaults = {
  title: 'TicketMaster',
  BASE_URL: window.location.origin,
  API_PATH: 'api',
  SERVICES: {
    ticketmaster: ''
  },
  authorization: 'disabled',
  hasHeaderTitle: false,
  help: 'https://github.com/TeskaLabs/asab-webui',
  defaultBrandImage: {
    full: 'media/logo/header-logo-full.svg',
    minimized: 'media/logo/header-logo-minimized.svg'
  },
  brandImage: {
    light: {
      full: 'media/logo/header-logo-full.svg',
      minimized: 'media/logo/header-logo-minimized.svg'
    },
    dark: {
      full: 'media/logo/header-logo-full-dark.svg',
      minimized: 'media/logo/header-logo-minimized-dark.svg'
    }
  },
  sidebarLogo: {
    light: {
      full: 'media/logo/header-logo-full.svg',
      minimized: 'media/logo/header-logo-minimized.svg'
    },
    dark: {
      full: 'media/logo/header-logo-full-dark.svg',
      minimized: 'media/logo/header-logo-minimized-dark.svg'
    }
  },
  i18n: {
    fallbackLng: 'en',
    supportedLngs: ['en'],
    debug: false
  }
};

createRoot(document.getElementById('app')).render(
  <ApplicationHashRouter>
    <Application
      modules={[I18nModule, TicketMasterModule]}
      configdefaults={ConfigDefaults}
    />
  </ApplicationHashRouter>
);
