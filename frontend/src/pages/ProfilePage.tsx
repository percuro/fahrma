import { useState, type FormEvent } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, errorText } from '../lib/api';
import type { Me } from '../lib/types';
import { ME_KEY } from '../hooks/useMe';
import { useSession } from '../hooks/useSession';
import { APP_NAME } from '../app/brand';
import { useFeedback } from '../components/feedback-context';
import { useT } from '../i18n';
import { CreateGroup } from './StartPage';
import { ChangePassword, DeleteAccount, Devices, MyData } from './AccountSections';
import { LegalLinks } from '../components/LegalLinks';

const LANGUAGE_NAMES = { de: 'Deutsch', en: 'English' } as const;

export function ProfilePage() {
  const t = useT();
  const me = useSession();
  return (
    <>
      <h1>{t.profile.title}</h1>
      <p className="subtle">{t.profile.signedInAs(me.username)}</p>
      <ProfileForm me={me} />
      {me.groups.length > 0 && (
        <section>
          <h2>{t.nav.switchGroup}</h2>
          <ul className="list card">
            {me.groups.map((g) => (
              <li key={g.id}><Link className="row" to={`/g/${g.id}`}><span className="main title">{g.name}</span></Link></li>
            ))}
          </ul>
        </section>
      )}
      <details className="mt-1">
        <summary className="link-button">{t.start.createAnother}</summary>
        <CreateGroup />
      </details>
      {me.role === 'admin' && (
        <p><Link className="button" to="/admin">{t.nav.admin}</Link></p>
      )}
      <ChangePassword />
      <Devices />
      <MyData />
      <Logout />
      <DeleteAccount />
      <p className="subtle version">{APP_NAME} {__APP_VERSION__}</p>
      <LegalLinks />
    </>
  );
}

function ProfileForm({ me }: { me: Me }) {
  const t = useT();
  const { toast } = useFeedback();
  const queryClient = useQueryClient();
  const [name, setName] = useState(me.display_name);
  const [locale, setLocale] = useState<string>(me.locale ?? '');
  const save = useMutation({
    mutationFn: () =>
      apiFetch<Me>('/v1/auth/me', {
        method: 'PATCH',
        body: JSON.stringify({ display_name: name.trim(), locale: locale || null }),
      }),
    onSuccess: (updated) => {
      queryClient.setQueryData(ME_KEY, updated);
      void queryClient.invalidateQueries({ queryKey: ['group'] });
      toast(t.common.saved);
    },
  });
  const changed = name.trim() !== me.display_name || (locale || null) !== me.locale;
  const submit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate();
  };
  return (
    <form className="card form" onSubmit={submit}>
      <label className="field">
        <span>{t.profile.displayName}</span>
        <input value={name} onChange={(e) => setName(e.target.value)} required maxLength={80} />
      </label>
      <label className="field">
        <span>{t.profile.language}</span>
        <select value={locale} onChange={(e) => setLocale(e.target.value)}>
          <option value="">{t.profile.languageAuto}</option>
          {Object.entries(LANGUAGE_NAMES).map(([code, label]) => (
            <option key={code} value={code} lang={code}>{label}</option>
          ))}
        </select>
      </label>
      {save.isError && <p className="error" role="alert">{errorText(save.error)}</p>}
      <button type="submit" className="button" disabled={save.isPending || !changed}>{t.common.save}</button>
    </form>
  );
}

function Logout() {
  const t = useT();
  const { confirm } = useFeedback();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const logout = useMutation({
    mutationFn: () => apiFetch<void>('/v1/auth/logout', { method: 'POST' }),
    onSuccess: () => {
      window.dispatchEvent(new Event('carshare:logout'));
      queryClient.clear();
      queryClient.setQueryData(ME_KEY, null);
      navigate('/');
    },
  });
  const onLogout = async () => {
    if (await confirm(t.auth.confirmLogout, { confirmLabel: t.auth.logout })) logout.mutate();
  };
  return (
    <div className="button-row">
      <button type="button" className="button" onClick={onLogout} disabled={logout.isPending}>{t.auth.logout}</button>
      {logout.isError && <p className="error" role="alert">{errorText(logout.error)}</p>}
    </div>
  );
}
