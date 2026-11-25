import { useEffect, useRef, useState } from 'react';
import { NavLink, Outlet, useParams } from 'react-router-dom';
import { useQueryClient } from '@tanstack/react-query';
import type { Me } from '../lib/types';
import { ME_KEY, useMe } from '../hooks/useMe';
import { SessionContext } from '../hooks/useSession';
import { useSetupStatus } from '../hooks/useSetupStatus';
import { isValidGroupId } from '../hooks/useGroupData';
import { LoginPage } from '../pages/LoginPage';
import { SetupPage } from '../pages/SetupPage';
import { APP_NAME } from '../app/brand';
import { useT } from '../i18n';
import { Loading } from './Status';
import { OfflineBanner, OfflineSync } from './OfflineSync';
import { clearCache } from '../lib/offline-cache';
import { removeUserDrafts } from '../lib/outbox';
import { CalendarIcon, HomeIcon, ListIcon, ScaleIcon, UserIcon, UsersIcon } from './Icons';

export function AppLayout() {
  const me = useMe();
  const t = useT();
  const queryClient = useQueryClient();
  // The last signed-in state: if the session expires, the page stays (with its input) behind the login dialog
  const [lastMe, setLastMe] = useState<Me | null>(null);
  if (me.data && me.data !== lastMe) setLastMe(me.data);
  const lastUserId = useRef<number | null>(null);
  useEffect(() => {
    if (lastMe) lastUserId.current = lastMe.id;
  }, [lastMe]);

  useEffect(() => {
    const onUnauthorized = () => queryClient.setQueryData(ME_KEY, null);
    // Logged out or account deleted: nothing of this person stays on the device
    const onLogout = () => {
      setLastMe(null);
      if (lastUserId.current !== null) removeUserDrafts(lastUserId.current);
      clearCache();
      queryClient.removeQueries({ queryKey: ['group'] });
    };
    window.addEventListener('carshare:unauthorized', onUnauthorized);
    window.addEventListener('carshare:logout', onLogout);
    return () => {
      window.removeEventListener('carshare:unauthorized', onUnauthorized);
      window.removeEventListener('carshare:logout', onLogout);
    };
  }, [queryClient]);

  if (me.isPending) return <main className="center"><Loading /></main>;
  // Offline with a known account (offline cache): the app works, entries become drafts
  if (me.data) return <SignedIn me={me.data} />;
  if (me.isError) {
    return (
      <main className="center">
        <p role="alert">{t.app.serverUnreachable}</p>
        <button type="button" className="button" onClick={() => me.refetch()}>{t.common.retry}</button>
      </main>
    );
  }
  if (lastMe) {
    return (
      <>
        <SignedIn me={lastMe} />
        <div className="overlay">
          <LoginPage notice={t.app.sessionExpired} />
        </div>
      </>
    );
  }
  return <SignedOut />;
}

/** Login, or the first-run setup while the instance has no account yet. */
function SignedOut() {
  const setup = useSetupStatus();
  if (setup.isPending) return <main className="center"><Loading /></main>;
  return setup.data?.needed ? <SetupPage /> : <LoginPage />;
}

function SignedIn({ me }: { me: Me }) {
  const t = useT();
  const { groupId } = useParams();
  const gid = groupId ? Number(groupId) : null;
  const inGroup = gid !== null && isValidGroupId(gid);

  return (
    <SessionContext.Provider value={me}>
      <a className="skip-link" href="#content">{t.nav.skip}</a>
      <UpdateBanner />
      <OfflineBanner />
      <OfflineSync />
      <header className="topbar">
        <NavLink to="/" className="brand">{APP_NAME}</NavLink>
        {inGroup && (
          <nav className="bottomnav" aria-label={t.nav.areas}>
            <NavLink to={`/g/${gid}`} end><HomeIcon />{t.nav.overview}</NavLink>
            <NavLink to={`/g/${gid}/calendar`}><CalendarIcon />{t.nav.calendar}</NavLink>
            <NavLink to={`/g/${gid}/history`}><ListIcon />{t.nav.history}</NavLink>
            <NavLink to={`/g/${gid}/settlement`}><ScaleIcon />{t.nav.settlement}</NavLink>
            <NavLink to={`/g/${gid}/group`}><UsersIcon />{t.nav.group}</NavLink>
          </nav>
        )}
        <span className="spacer" />
        <NavLink to="/profile" className="icon-link" aria-label={t.nav.profile}>
          <UserIcon />
        </NavLink>
      </header>
      <main id="content" className="content">
        <Outlet />
      </main>
    </SessionContext.Provider>
  );
}

/** Offers a reload when the service worker has a new version (see main.tsx). */
function UpdateBanner() {
  const t = useT();
  const [available, setAvailable] = useState(false);
  useEffect(() => {
    const show = () => setAvailable(true);
    window.addEventListener('carshare:update-available', show);
    return () => window.removeEventListener('carshare:update-available', show);
  }, []);
  if (!available) return null;
  return (
    <div className="update-banner" role="status">
      <span>{t.app.updateAvailable}</span>
      <button type="button" className="button small primary" onClick={() => window.dispatchEvent(new Event('carshare:apply-update'))}>
        {t.app.reload}
      </button>
    </div>
  );
}
