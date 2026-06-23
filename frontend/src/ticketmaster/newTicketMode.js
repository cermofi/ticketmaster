export function resolveNewTicketInitialMode(user, targetParam) {
  if (user?.kind !== 'internal') return 'partner';
  return targetParam === 'partner' ? 'partner' : 'internal';
}

export function availableNewTicketModes(user) {
  if (user?.kind === 'partner') return ['partner'];
  return ['internal', 'partner'];
}

export function isNewTicketModeVisible(user, mode) {
  return availableNewTicketModes(user).includes(mode);
}
