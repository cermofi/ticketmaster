import { lazy } from 'react';
import { Module } from 'asab_webui_components';
import LanguageDropdown from 'asab_webui_shell/dist/modules/i18n/dropdown.js';

const DashboardScreen = lazy(() => import('./screens/DashboardScreen.jsx'));
const GitLabDeliveryTrackingScreen = lazy(() => import('./screens/GitLabDeliveryTrackingScreen.jsx'));
const GitLabDeliveryIssueDetailScreen = lazy(() => import('./screens/GitLabDeliveryIssueDetailScreen.jsx'));
const NewTicketScreen = lazy(() => import('./screens/NewTicketScreen.jsx'));
const TicketDetailScreen = lazy(() => import('./screens/TicketDetailScreen.jsx'));
const PartnerOverviewScreen = lazy(() => import('./screens/PartnerOverviewScreen.jsx'));
const AdminScreen = lazy(() => import('./screens/AdminScreen.jsx'));
const AuditScreen = lazy(() => import('./screens/AuditScreen.jsx'));
const SettingsScreen = lazy(() => import('./screens/SettingsScreen.jsx'));
const AccountSettingsScreen = lazy(() => import('./screens/AccountSettingsScreen.jsx'));
const ChangePasswordScreen = lazy(() => import('./screens/ChangePasswordScreen.jsx'));

export default class TicketMasterModule extends Module {
  constructor(app) {
    super(app, 'TicketMasterModule');

    app.Router.addRoute({ path: '/', end: true, name: 'Tickets', component: GitLabDeliveryTrackingScreen, resource: '*' });
    app.Router.addRoute({ path: '/tickets', end: true, name: 'Tickets', component: GitLabDeliveryTrackingScreen, resource: '*' });
    app.Router.addRoute({ path: '/tickets/:trackedIssueId', end: true, name: 'Ticket detail', component: GitLabDeliveryIssueDetailScreen, resource: '*' });
    app.Router.addRoute({ path: '/delivery-tracking', end: true, name: 'Tickets', component: GitLabDeliveryTrackingScreen, resource: '*' });
    app.Router.addRoute({ path: '/delivery-tracking/:trackedIssueId', end: true, name: 'Ticket detail', component: GitLabDeliveryIssueDetailScreen, resource: '*' });
    app.Router.addRoute({ path: '/legacy-tickets', end: true, name: 'Legacy tickets', component: DashboardScreen, resource: '*' });
    app.Router.addRoute({ path: '/legacy-tickets/new', end: true, name: 'Create legacy ticket', component: NewTicketScreen, resource: '*' });
    app.Router.addRoute({ path: '/legacy-tickets/:ticketId', end: true, name: 'Legacy ticket detail', component: TicketDetailScreen, resource: '*' });
    app.Router.addRoute({ path: '/partner-overview', end: true, name: 'Partner overview', component: PartnerOverviewScreen, resource: '*' });
    app.Router.addRoute({ path: '/admin', end: true, name: 'Admin', component: AdminScreen, resource: '*' });
    app.Router.addRoute({ path: '/audit', end: true, name: 'Audit', component: AuditScreen, resource: '*' });
    app.Router.addRoute({ path: '/account', end: true, name: 'Account settings', component: AccountSettingsScreen, resource: '*' });
    app.Router.addRoute({ path: '/account/password', end: true, name: 'Change password', component: ChangePasswordScreen, resource: '*' });
    app.Router.addRoute({ path: '/settings', end: true, name: 'Settings', component: SettingsScreen, resource: '*' });

    app.Navigation.addItem({ name: 'Tickets', url: '/', icon: 'bi bi-ticket-detailed' });
    app.Navigation.addItem({ name: 'Admin', url: '/admin', icon: 'bi bi-sliders' });
    app.Navigation.addItem({ name: 'Audit', url: '/audit', icon: 'bi bi-journal-check' });
    app.Navigation.addItem({ name: 'Settings', url: '/settings', icon: 'bi bi-gear' });
  }

  initialize() {
    const headerService = this.App.locateService('HeaderService');
    headerService?.removeComponent(LanguageDropdown);
  }
}
