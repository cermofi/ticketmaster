export function getInternalRoles(user) {
  if (!user || user.kind !== 'internal') return [];
  if (Array.isArray(user.internal_roles) && user.internal_roles.length) return user.internal_roles;
  if (user.internal_role) return [user.internal_role];
  return [];
}

export function hasAnyInternalRole(user, roles) {
  const internalRoles = getInternalRoles(user);
  return roles.some((role) => internalRoles.includes(role));
}

export function canSignInAsPartner(user) {
  return user?.kind === 'internal' && hasAnyInternalRole(user, ['Admin', 'DeliveryManager']);
}

export function canReturnToAdmin(user, hasReturnToken) {
  return user?.kind === 'partner' && Boolean(hasReturnToken);
}
