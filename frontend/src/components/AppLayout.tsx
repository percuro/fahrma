import { useEffect, useRef, useState, type ReactNode } from 'react';
import { NavLink, Outlet, useLocation, useNavigationType, useParams } from 'react-router-dom';
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
import { discardUserPhotos } from '../lib/photo-outbox';
import { unsubscribeLocally } from '../lib/push';
import { CalendarIcon, HomeIcon, ListIcon, ScaleIcon, UserIcon, UsersIcon } from './Icons';
import { BrandMark } from './BrandMark';

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
      if (lastUserId.current !== null) {
        removeUserDrafts(lastUserId.current);
        void discardUserPhotos(lastUserId.current);
      }
      clearCache();
      // The server ended this device's subscription with the login
      void unsubscribeLocally();
      queryClient.removeQueries({ queryKey: ['group'] });
      queryClient.removeQueries({ queryKey: ['notifications'] });
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
  usePageChange();

  return (
    <SessionContext.Provider value={me}>
      <a className="skip-link" href="#content">{t.nav.skip}</a>
      <header className="topbar">
        <NavLink to="/" className="brand"><BrandMark />{APP_NAME}</NavLink>
        {inGroup && (
          <nav className="appnav" aria-label={t.nav.areas}>
            <NavItem to={`/g/${gid}`} end icon={<HomeIcon />}>{t.nav.overview}</NavItem>
            <NavItem to={`/g/${gid}/calendar`} icon={<CalendarIcon />}>{t.nav.calendar}</NavItem>
            <NavItem to={`/g/${gid}/history`} icon={<ListIcon />}>{t.nav.history}</NavItem>
            <NavItem to={`/g/${gid}/settlement`} icon={<ScaleIcon />}>{t.nav.settlement}</NavItem>
            <NavItem to={`/g/${gid}/group`} icon={<UsersIcon />}>{t.nav.group}</NavItem>
          </nav>
        )}
        <span className="spacer" />
        <NavLink to="/profile" className="icon-button" aria-label={t.nav.profile}>
          <UserIcon />
        </NavLink>
      </header>
      <UpdateBanner />
      <OfflineBanner />
      <OfflineSync />
      {/* Screen readers hear the name of the page after a change of page */}
      <p id={ANNOUNCER_ID} className="sr-only" role="status" />
      <main id="content" className="content" tabIndex={-1}>
        <Outlet />
      </main>
    </SessionContext.Provider>
  );
}

/** One place of the navigation: icon and a short word; the active one gets the highlight. */
function NavItem({ to, end, icon, children }: { to: string; end?: boolean; icon: ReactNode; children: ReactNode }) {
  return (
    <NavLink to={to} end={end}>
      <span className="nav-icon">{icon}</span>
      <span className="nav-label">{children}</span>
    </NavLink>
  );
}

/**
 * The window title follows the heading of the page ("Trip · fahrma"): an installed
 * app shows it in its window and in the task switcher, a browser in its tab.
 *
 * After a change of page (not on the first load, not after a redirect) the focus moves to the
 * start of the content, as after a page load, and the new heading is announced once it shows.
 */
const ANNOUNCER_ID = 'page-announcer';

function announce(text: string) {
  const region = document.getElementById(ANNOUNCER_ID);
  if (region) region.textContent = text;
}

function usePageChange() {
  const { pathname } = useLocation();
  const navigationType = useNavigationType();
  const firstPath = useRef(true);
  const announcePending = useRef(false);

  useEffect(() => {
    if (firstPath.current) {
      firstPath.current = false;
      return;
    }
    if (navigationType === 'REPLACE') return;
    const main = document.getElementById('content');
    main?.focus({ preventScroll: true });
    // A page that still loads its data gets its heading later; the observer below announces it then
    const heading = main?.querySelector('h1')?.textContent?.trim();
    announcePending.current = !heading;
    announce(heading ?? '');
  }, [pathname, navigationType]);

  useEffect(() => {
    const main = document.getElementById('content');
    if (!main) return;
    const update = () => {
      const heading = main.querySelector('h1')?.textContent?.trim();
      const title = heading ? `${heading} · ${APP_NAME}` : APP_NAME;
      if (document.title !== title) document.title = title;
      if (heading && announcePending.current) {
        announcePending.current = false;
        announce(heading);
      }
    };
    update();
    const observer = new MutationObserver(update);
    observer.observe(main, { childList: true, subtree: true, characterData: true });
    return () => {
      observer.disconnect();
      document.title = APP_NAME;
    };
  }, []);
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
    <div className="banner" role="status">
      <span>{t.app.updateAvailable}</span>
      <button type="button" className="button small primary" onClick={() => window.dispatchEvent(new Event('carshare:apply-update'))}>
        {t.app.reload}
      </button>
    </div>
  );
}
