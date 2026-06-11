import { lazy } from 'react';
import { Module } from 'asab_webui_components';

const DashboardScreen = lazy(() => import('./screens/DashboardScreen.jsx'));
const NewTicketScreen = lazy(() => import('./screens/NewTicketScreen.jsx'));
const TicketDetailScreen = lazy(() => import('./screens/TicketDetailScreen.jsx'));
const PartnerOverviewScreen = lazy(() => import('./screens/PartnerOverviewScreen.jsx'));
const AdminScreen = lazy(() => import('./screens/AdminScreen.jsx'));
const AuditScreen = lazy(() => import('./screens/AuditScreen.jsx'));
const SettingsScreen = lazy(() => import('./screens/SettingsScreen.jsx'));

export default class TicketMasterModule extends Module {
  constructor(app) {
    super(app, 'TicketMasterModule');

    app.Router.addRoute({ path: '/', end: true, name: 'Tickety', component: DashboardScreen, resource: '*' });
    app.Router.addRoute({ path: '/tickets/new', end: true, name: 'Vytvořit ticket', component: NewTicketScreen, resource: '*' });
    app.Router.addRoute({ path: '/tickets/:ticketId', end: true, name: 'Detail ticketu', component: TicketDetailScreen, resource: '*' });
    app.Router.addRoute({ path: '/partner-overview', end: true, name: 'Přehled klientů', component: PartnerOverviewScreen, resource: '*' });
    app.Router.addRoute({ path: '/admin', end: true, name: 'Admin', component: AdminScreen, resource: '*' });
    app.Router.addRoute({ path: '/audit', end: true, name: 'Audit', component: AuditScreen, resource: '*' });
    app.Router.addRoute({ path: '/settings', end: true, name: 'Nastavení', component: SettingsScreen, resource: '*' });

    app.Navigation.addItem({ name: 'Tickety', url: '/', icon: 'bi bi-ticket-detailed' });
    app.Navigation.addItem({ name: 'Vytvořit ticket', url: '/tickets/new', icon: 'bi bi-plus-square' });
    app.Navigation.addItem({ name: 'Přehled klientů', url: '/partner-overview', icon: 'bi bi-building' });
    app.Navigation.addItem({ name: 'Admin', url: '/admin', icon: 'bi bi-sliders' });
    app.Navigation.addItem({ name: 'Audit', url: '/audit', icon: 'bi bi-journal-check' });
    app.Navigation.addItem({ name: 'Nastavení', url: '/settings', icon: 'bi bi-gear' });
  }
}
