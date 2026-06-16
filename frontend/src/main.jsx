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

const BRAND_IMAGE_SELECTOR = '#app-brandimage a, #app-sidebar-logo';

function neutralizeBrandImageNodes(root = document) {
  root.querySelectorAll(BRAND_IMAGE_SELECTOR).forEach((node) => {
    if (node.style.backgroundImage) {
      node.style.backgroundImage = 'none';
    }
    node.querySelectorAll('img').forEach((img) => img.remove());
  });
}

function installBrandImageGuard() {
  neutralizeBrandImageNodes();

  const observer = new MutationObserver((mutations) => {
    for (const mutation of mutations) {
      if (mutation.type === 'attributes' && mutation.target.matches?.(BRAND_IMAGE_SELECTOR)) {
        neutralizeBrandImageNodes(mutation.target.parentElement || document);
        continue;
      }
      mutation.addedNodes.forEach((node) => {
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        if (node.matches?.(BRAND_IMAGE_SELECTOR) || node.querySelector?.(BRAND_IMAGE_SELECTOR)) {
          neutralizeBrandImageNodes(node);
        }
      });
    }
  });

  observer.observe(document.documentElement, {
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ['style']
  });
}

installBrandImageGuard();

function releaseBootModeWhenReady() {
  let resolved = false;
  const appRoot = document.getElementById('app');
  const loader = document.getElementById('tm-global-loader');
  let observer = null;
  let timeoutId = 0;

  const cleanup = () => {
    window.removeEventListener('tm:dashboard-ready', resolveBootMode);
    window.removeEventListener('tm:auth-ready', resolveBootMode);
    observer?.disconnect();
    if (timeoutId) {
      window.clearTimeout(timeoutId);
    }
  };

  const clearBootMode = () => {
    document.body.classList.remove('tm-app-booting');
    loader?.remove();
  };

  function resolveBootMode() {
    if (resolved) return;
    resolved = true;
    cleanup();
    clearBootMode();
  }

  const isDashboardReady = () => (
    document.querySelector('.tm-page-header h1')?.textContent?.trim() === 'Tickets'
    && !document.querySelector('.tm-loading-state')
  );

  const isLoginReady = () => Boolean(document.querySelector('.tm-login'));
  const tryResolve = () => {
    if (isDashboardReady() || isLoginReady()) {
      resolveBootMode();
    }
  };

  window.addEventListener('tm:dashboard-ready', resolveBootMode);
  window.addEventListener('tm:auth-ready', resolveBootMode);

  if (!appRoot) {
    resolveBootMode();
    return;
  }

  observer = new MutationObserver(() => {
    tryResolve();
  });
  observer.observe(appRoot, { childList: true, subtree: true, characterData: true });

  timeoutId = window.setTimeout(() => {
    resolveBootMode();
  }, 15000);

  tryResolve();
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
