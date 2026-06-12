import React from 'react';
import { createRoot } from 'react-dom/client';
import { Application, ApplicationHashRouter, I18nModule } from 'asab_webui_shell';

import 'bootstrap/dist/css/bootstrap.min.css';
import 'bootstrap-icons/font/bootstrap-icons.css';
import './styles.scss';

import TicketMasterModule from './ticketmaster/TicketMasterModule.jsx';

const CHUNK_RELOAD_KEY = 'ticketmaster.chunk_reload_attempt';
const CHUNK_RELOAD_COOLDOWN_MS = 30000;

function extractErrorMessage(reason) {
  if (!reason) return '';
  if (typeof reason === 'string') return reason;
  if (reason instanceof Error) return reason.message || '';
  if (typeof reason.message === 'string') return reason.message;
  return String(reason);
}

function isChunkLoadFailure(message) {
  if (!message) return false;
  return (
    /failed to fetch dynamically imported module/i.test(message)
    || /importing a module script failed/i.test(message)
    || /loading chunk [\d]+ failed/i.test(message)
    || /chunkloaderror/i.test(message)
  );
}

function shouldReloadForChunkError() {
  const now = Date.now();
  const currentLocation = `${window.location.pathname}${window.location.hash}`;
  try {
    const raw = sessionStorage.getItem(CHUNK_RELOAD_KEY);
    if (raw) {
      const parsed = JSON.parse(raw);
      if (
        parsed
        && parsed.location === currentLocation
        && now - Number(parsed.at || 0) < CHUNK_RELOAD_COOLDOWN_MS
      ) {
        return false;
      }
    }
    sessionStorage.setItem(CHUNK_RELOAD_KEY, JSON.stringify({ location: currentLocation, at: now }));
  } catch {
    // If sessionStorage is blocked, fail open and still try one reload.
  }
  return true;
}

function installChunkRecovery() {
  const recover = (message) => {
    if (!isChunkLoadFailure(message)) return;
    if (shouldReloadForChunkError()) {
      window.location.reload();
    }
  };

  window.addEventListener('unhandledrejection', (event) => {
    recover(extractErrorMessage(event?.reason));
  });

  window.addEventListener('error', (event) => {
    recover(extractErrorMessage(event?.error || event?.message));
  }, true);
}

installChunkRecovery();

function releaseBootModeWhenReady() {
  const clearBootMode = () => document.body.classList.remove('tm-app-booting');
  const appRoot = document.getElementById('app');
  if (!appRoot) {
    clearBootMode();
    return;
  }

  const appReady = () => (
    Boolean(document.querySelector('#app-main'))
    && !document.querySelector('.tm-loading-state')
  );

  if (appReady()) {
    clearBootMode();
    return;
  }

  const observer = new MutationObserver(() => {
    if (!appReady()) return;
    clearBootMode();
    observer.disconnect();
  });

  observer.observe(appRoot, { childList: true, subtree: true, attributes: true });
  window.setTimeout(() => {
    clearBootMode();
    observer.disconnect();
  }, 6000);
}

const ConfigDefaults = {
  title: 'TicketMaster',
  BASE_URL: window.location.origin,
  API_PATH: 'api',
  SERVICES: {
    ticketmaster: ''
  },
  authorization: 'disabled',
  hasHeaderTitle: false,
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

releaseBootModeWhenReady();
