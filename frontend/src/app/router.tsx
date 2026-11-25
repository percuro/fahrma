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
import { ProfilePage } from '../pages/ProfilePage';

const legacy = ['fahrt/*', 'tanken/*', 'kosten/*', 'verlauf', 'abrechnung', 'abrechnung/*', 'gruppe'].map((path) => ({
  path: `g/:groupId/${path}`,
  element: <LegacyRedirect />,
}));

export const router = createBrowserRouter([
  // Invitation: reachable without login (registration)
  { path: '/invite/:token', element: <InvitePage /> },
  { path: '/einladung/:token', element: <LegacyInviteRedirect /> },
  {
    path: '/',
    element: <AppLayout />,
    children: [
      { index: true, element: <StartPage /> },
      { path: 'profile', element: <ProfilePage /> },
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
      ...legacy,
      { path: '*', element: <Navigate to="/" replace /> },
    ],
  },
]);
