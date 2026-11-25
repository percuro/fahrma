import { createBrowserRouter, Navigate } from 'react-router-dom';
import { LegacyRedirect } from '../components/LegacyRedirect';
import { AppLayout } from '../components/AppLayout';
import { StartPage } from '../pages/StartPage';
import { InvitePage, LegacyInviteRedirect } from '../pages/InvitePage';
import { DashboardPage } from '../pages/DashboardPage';
import { TripFormPage } from '../pages/TripFormPage';
import { FuelFormPage } from '../pages/FuelFormPage';
import { ExpenseFormPage } from '../pages/ExpenseFormPage';
import { HistoryPage } from '../pages/HistoryPage';
import { SettlementPage } from '../pages/SettlementPage';
import { SettlementDetailPage } from '../pages/SettlementDetailPage';
import { GroupPage } from '../pages/GroupPage';
import { StatsPage } from '../pages/StatsPage';
import { CalendarPage } from '../pages/CalendarPage';
import { ReservationFormPage } from '../pages/ReservationFormPage';
import { ProfilePage } from '../pages/ProfilePage';
import { RegisterPage } from '../pages/RegisterPage';
import { AdminPage } from '../pages/AdminPage';
import { ImportPage } from '../pages/ImportPage';
import { ForgotPasswordPage } from '../pages/ForgotPasswordPage';

const legacy = ['fahrt/*', 'tanken/*', 'kosten/*', 'verlauf', 'abrechnung', 'abrechnung/*', 'gruppe'].map((path) => ({
  path: `g/:groupId/${path}`,
  element: <LegacyRedirect />,
}));

export const router = createBrowserRouter([
  // One-time links (token in the fragment) and registration: reachable without login
  { path: '/invite', element: <InvitePage /> },
  { path: '/invite/:token', element: <LegacyInviteRedirect /> },
  { path: '/einladung/:token', element: <LegacyInviteRedirect /> },
  { path: '/register', element: <RegisterPage /> },
  { path: '/forgot-password', element: <ForgotPasswordPage /> },
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <StartPage /> },
      { path: 'profile', element: <ProfilePage /> },
      { path: 'admin', element: <AdminPage /> },
      { path: 'import', element: <ImportPage /> },
      { path: 'g/:groupId', element: <DashboardPage /> },
      { path: 'g/:groupId/trip/new', element: <TripFormPage /> },
      { path: 'g/:groupId/trip/:tripId', element: <TripFormPage /> },
      { path: 'g/:groupId/fuel/new', element: <FuelFormPage /> },
      { path: 'g/:groupId/fuel/:fuelId', element: <FuelFormPage /> },
      { path: 'g/:groupId/expense/new', element: <ExpenseFormPage /> },
      { path: 'g/:groupId/expense/:expenseId', element: <ExpenseFormPage /> },
      { path: 'g/:groupId/history', element: <HistoryPage /> },
      { path: 'g/:groupId/settlement', element: <SettlementPage /> },
      { path: 'g/:groupId/settlement/:settlementId', element: <SettlementDetailPage /> },
      { path: 'g/:groupId/group', element: <GroupPage /> },
      { path: 'g/:groupId/stats', element: <StatsPage /> },
      { path: 'g/:groupId/calendar', element: <CalendarPage /> },
      { path: 'g/:groupId/reservation/new', element: <ReservationFormPage /> },
      { path: 'g/:groupId/reservation/:reservationId', element: <ReservationFormPage /> },
      ...legacy,
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
