import { SESSION_CHANGE_EVENT } from './client.js';

/** Data domains fetched by primary screens. */
export const DATA_DOMAINS = Object.freeze({
  session: 'session',
  meta: 'meta',
  tickets: 'tickets',
  ticketDetail: 'ticketDetail',
  audit: 'audit',
  gitlabDeliveryTracking: 'gitlabDeliveryTracking',
  admin: 'admin',
  account: 'account',
  partners: 'partners',
  clients: 'clients',
  users: 'users',
  partnerOverview: 'partnerOverview'
});

/** Session lifecycle transitions that trigger domain invalidation. */
export const SESSION_TRANSITIONS = Object.freeze({
  login: 'login',
  logout: 'logout',
  impersonationStart: 'impersonationStart',
  impersonationEnd: 'impersonationEnd',
  sessionRefresh: 'sessionRefresh'
});

/**
 * Explicit invalidation map: transition → domains to reset/refetch.
 * Hard reload is never listed here; screens refetch via registered invalidators.
 */
export const INVALIDATION_MAP = Object.freeze({
  [SESSION_TRANSITIONS.login]: [
    DATA_DOMAINS.session,
    DATA_DOMAINS.meta,
    DATA_DOMAINS.tickets,
    DATA_DOMAINS.ticketDetail,
    DATA_DOMAINS.audit,
    DATA_DOMAINS.gitlabDeliveryTracking,
    DATA_DOMAINS.admin,
    DATA_DOMAINS.account,
    DATA_DOMAINS.partners,
    DATA_DOMAINS.clients,
    DATA_DOMAINS.users,
    DATA_DOMAINS.partnerOverview
  ],
  [SESSION_TRANSITIONS.logout]: Object.values(DATA_DOMAINS),
  [SESSION_TRANSITIONS.impersonationStart]: [
    DATA_DOMAINS.session,
    DATA_DOMAINS.meta,
    DATA_DOMAINS.tickets,
    DATA_DOMAINS.ticketDetail,
    DATA_DOMAINS.audit,
    DATA_DOMAINS.gitlabDeliveryTracking,
    DATA_DOMAINS.admin,
    DATA_DOMAINS.account,
    DATA_DOMAINS.partners,
    DATA_DOMAINS.clients,
    DATA_DOMAINS.users,
    DATA_DOMAINS.partnerOverview
  ],
  [SESSION_TRANSITIONS.impersonationEnd]: [
    DATA_DOMAINS.session,
    DATA_DOMAINS.meta,
    DATA_DOMAINS.tickets,
    DATA_DOMAINS.ticketDetail,
    DATA_DOMAINS.audit,
    DATA_DOMAINS.gitlabDeliveryTracking,
    DATA_DOMAINS.admin,
    DATA_DOMAINS.account,
    DATA_DOMAINS.partners,
    DATA_DOMAINS.clients,
    DATA_DOMAINS.users,
    DATA_DOMAINS.partnerOverview
  ],
  [SESSION_TRANSITIONS.sessionRefresh]: [
    DATA_DOMAINS.session,
    DATA_DOMAINS.account
  ]
});

const domainInvalidators = new Map();
const LEGACY_ALL = '*';

export function registerDomainInvalidator(domain, invalidator) {
  if (!domainInvalidators.has(domain)) {
    domainInvalidators.set(domain, new Set());
  }
  const bucket = domainInvalidators.get(domain);
  bucket.add(invalidator);
  return () => bucket.delete(invalidator);
}

function runBucket(bucket) {
  bucket.forEach((invalidator) => {
    try {
      invalidator();
    } catch {
      // Domain invalidation must not block session changes.
    }
  });
}

export function invalidateDomains(domains) {
  const unique = [...new Set(domains)];
  unique.forEach((domain) => {
    const bucket = domainInvalidators.get(domain);
    if (bucket) runBucket(bucket);
  });
  const legacy = domainInvalidators.get(LEGACY_ALL);
  if (legacy) runBucket(legacy);
  window.dispatchEvent(new Event(SESSION_CHANGE_EVENT));
}

export function invalidateForTransition(transition) {
  const domains = INVALIDATION_MAP[transition];
  if (!domains) return;
  invalidateDomains(domains);
}

export function invalidateAllDomains() {
  invalidateDomains(Object.values(DATA_DOMAINS));
}
