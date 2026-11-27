import { createBrowserRouter, Navigate } from 'react-router-dom';
import { LegacyRedirect } from '../components/LegacyRedirect';
import { AppLayout } from '../components/AppLayout';
import { Loading, PageFailed } from '../components/Status';
import { StartPage } from '../pages/StartPage';
import { DashboardPage } from '../pages/DashboardPage';
import { TripFormPage } from '../pages/TripFormPage';
import { lazyPage } from './lazy';

// The start, the group's overview and the trip form are what people open most, so they are in
// the main chunk. Every other page is its own chunk, loaded on first use; the service worker
// precaches all of them, so the app works offline as before.
const page = {
  invite: lazyPage(() => import('../pages/InvitePage'), (m) => m.InvitePage),
  legacyInvite: lazyPage(() => import('../pages/InvitePage'), (m) => m.LegacyInviteRedirect),
  register: lazyPage(() => import('../pages/RegisterPage'), (m) => m.RegisterPage),
  forgotPassword: lazyPage(() => import('../pages/ForgotPasswordPage'), (m) => m.ForgotPasswordPage),
  profile: lazyPage(() => import('../pages/ProfilePage'), (m) => m.ProfilePage),
  admin: lazyPage(() => import('../pages/AdminPage'), (m) => m.AdminPage),
  import: lazyPage(() => import('../pages/ImportPage'), (m) => m.ImportPage),
  fuel: lazyPage(() => import('../pages/FuelFormPage'), (m) => m.FuelFormPage),
  expense: lazyPage(() => import('../pages/ExpenseFormPage'), (m) => m.ExpenseFormPage),
  history: lazyPage(() => import('../pages/HistoryPage'), (m) => m.HistoryPage),
  settlement: lazyPage(() => import('../pages/SettlementPage'), (m) => m.SettlementPage),
  settlementDetail: lazyPage(() => import('../pages/SettlementDetailPage'), (m) => m.SettlementDetailPage),
  group: lazyPage(() => import('../pages/GroupPage'), (m) => m.GroupPage),
  stats: lazyPage(() => import('../pages/StatsPage'), (m) => m.StatsPage),
  calendar: lazyPage(() => import('../pages/CalendarPage'), (m) => m.CalendarPage),
  reservation: lazyPage(() => import('../pages/ReservationFormPage'), (m) => m.ReservationFormPage),
};

const legacy = ['fahrt/*', 'tanken/*', 'kosten/*', 'verlauf', 'abrechnung', 'abrechnung/*', 'gruppe'].map((path) => ({
  path: `g/:groupId/${path}`,
  element: <LegacyRedirect />,
}));

// Pages without the app's frame: one-time links (token in the fragment) and registration
const standalone = { HydrateFallback: Loading, errorElement: <PageFailed /> };

export const router = createBrowserRouter([
  { path: '/invite', lazy: page.invite, ...standalone },
  { path: '/invite/:token', lazy: page.legacyInvite, ...standalone },
  { path: '/einladung/:token', lazy: page.legacyInvite, ...standalone },
  { path: '/register', lazy: page.register, ...standalone },
  { path: '/forgot-password', lazy: page.forgotPassword, ...standalone },
  {
    path: '/',
    element: <AppLayout />,
    HydrateFallback: Loading,
    children: [
      {
        // A page that fails to load shows inside the frame, with the navigation still there
        errorElement: <PageFailed />,
        children: [
          { index: true, element: <StartPage /> },
          { path: 'profile', lazy: page.profile },
          { path: 'admin', lazy: page.admin },
          { path: 'import', lazy: page.import },
          { path: 'g/:groupId', element: <DashboardPage /> },
          { path: 'g/:groupId/trip/new', element: <TripFormPage /> },
          { path: 'g/:groupId/trip/:tripId', element: <TripFormPage /> },
          { path: 'g/:groupId/fuel/new', lazy: page.fuel },
          { path: 'g/:groupId/fuel/:fuelId', lazy: page.fuel },
          { path: 'g/:groupId/expense/new', lazy: page.expense },
          { path: 'g/:groupId/expense/:expenseId', lazy: page.expense },
          { path: 'g/:groupId/history', lazy: page.history },
          { path: 'g/:groupId/settlement', lazy: page.settlement },
          { path: 'g/:groupId/settlement/:settlementId', lazy: page.settlementDetail },
          { path: 'g/:groupId/group', lazy: page.group },
          { path: 'g/:groupId/stats', lazy: page.stats },
          { path: 'g/:groupId/calendar', lazy: page.calendar },
          { path: 'g/:groupId/reservation/new', lazy: page.reservation },
          { path: 'g/:groupId/reservation/:reservationId', lazy: page.reservation },
          ...legacy,
          { path: '*', element: <Navigate to="/" replace /> },
        ],
      },
    ],
  },
]);
