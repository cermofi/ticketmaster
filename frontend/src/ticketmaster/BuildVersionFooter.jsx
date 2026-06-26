import React, { useEffect, useMemo, useState } from 'react';
import { createPortal } from 'react-dom';

const FOOTER_SELECTORS = [
  '#app-footer',
  '#app > footer',
  '#app .app-footer',
  '#app .footer'
];

const VERSION_RAW = String(import.meta.env.VITE_APP_VERSION || '').trim();

function resolveFooterHost() {
  for (const selector of FOOTER_SELECTORS) {
    const node = document.querySelector(selector);
    if (node) return node;
  }
  return null;
}

function formatVersionLabel(rawValue) {
  if (!rawValue) return 'Version unknown';
  if (rawValue.startsWith('sha-')) {
    return `Version ${rawValue.slice(4, 11)}`;
  }
  return `Version ${rawValue}`;
}

export default function BuildVersionFooter() {
  const [footerHost, setFooterHost] = useState(null);

  useEffect(() => {
    const updateHost = () => setFooterHost(resolveFooterHost());
    updateHost();

    const observer = new MutationObserver(() => updateHost());
    observer.observe(document.body, { childList: true, subtree: true });
    return () => observer.disconnect();
  }, []);

  const label = useMemo(() => formatVersionLabel(VERSION_RAW), []);
  const className = `tm-build-version${footerHost ? ' tm-build-version-inline' : ''}`;

  const content = (
    <div className={className} title={VERSION_RAW || 'version not available'}>
      {label}
    </div>
  );

  if (footerHost) {
    return createPortal(content, footerHost);
  }
  return content;
}
