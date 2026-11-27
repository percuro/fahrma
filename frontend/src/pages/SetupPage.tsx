import { useState, type FormEvent } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, errorText } from '../lib/api';
import type { Me } from '../lib/types';
import { ME_KEY } from '../hooks/useMe';
import { useT } from '../i18n';
import { useMeta } from '../hooks/useMeta';
import { OidcButton } from '../components/OidcButton';
import { useCallbackParams } from '../hooks/useCallbackParams';
import { callbackErrorText } from '../lib/oidc';

/** First-run setup: create the first account with the token from the server log. */
export function SetupPage() {
  const t = useT();
  const queryClient = useQueryClient();
  const [token, setToken] = useState('');
  const [username, setUsername] = useState('');
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const mismatch = confirm.length > 0 && password !== confirm;
  const meta = useMeta();
  const passwords = meta.data?.password_login !== false;
  const oidc = !!meta.data?.oidc;
  const [missing, setMissing] = useState(false);
  const callback = useCallbackParams();
  /** The first account through the provider: token, name and username, no password. */
  const providerBody = () => {
    if (!token.trim() || !/^[A-Za-z0-9._-]{2,80}$/.test(username.trim())) {
      setMissing(true);
      return null;
    }
    setMissing(false);
    return { token: token.trim(), username: username.trim(), display_name: displayName.trim() || null };
  };

  const setup = useMutation({
    mutationFn: () =>
      apiFetch<Me>('/v1/setup', {
        method: 'POST',
        body: JSON.stringify({
          token: token.trim(),
          username: username.trim(),
          display_name: displayName.trim() || null,
          password,
        }),
      }),
    onSuccess: (me) => {
      queryClient.setQueryData(['setup'], { needed: false });
      queryClient.setQueryData(ME_KEY, me);
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (password !== confirm) return;
    setup.mutate();
  };

  return (
    <main className="center">
      <form className="card login" onSubmit={submit}>
        <h1>{t.setup.title}</h1>
        <p className="subtle m-0">
          {t.setup.intro} (<code>docker compose logs app</code>).
        </p>
        <label className="field">
          <span>{t.setup.token}</span>
          <input name="setup-token" autoComplete="off" autoCapitalize="none" spellCheck={false} required
            value={token} onChange={(e) => setToken(e.target.value)} />
        </label>
        <label className="field">
          <span>{t.setup.displayName}</span>
          <input name="name" autoComplete="name" maxLength={80}
            value={displayName} onChange={(e) => setDisplayName(e.target.value)} />
        </label>
        <label className="field">
          <span>{t.auth.username}</span>
          <input name="username" autoComplete="username" autoCapitalize="none" required minLength={2} maxLength={80}
            pattern="[A-Za-z0-9._\-]+" title={t.auth.usernameHint}
            value={username} onChange={(e) => setUsername(e.target.value)} />
        </label>
        {passwords && <>
        <label className="field">
          <span>{t.auth.passwordMin}</span>
          <input name="new-password" type="password" autoComplete="new-password" required minLength={12}
            value={password} onChange={(e) => setPassword(e.target.value)} />
        </label>
        <label className="field">
          <span>{t.auth.passwordRepeat}</span>
          <input name="confirm-password" type="password" autoComplete="new-password" required
            aria-invalid={mismatch} aria-describedby={mismatch ? 'setup-mismatch' : undefined}
            value={confirm} onChange={(e) => setConfirm(e.target.value)} />
        </label>
        {mismatch && <p id="setup-mismatch" className="error" role="alert">{t.auth.passwordMismatch}</p>}
        </>}
        {setup.isError && <p className="error" role="alert">{errorText(setup.error)}</p>}
        {callback.error && (
          <p className="error" role="alert">{callbackErrorText(callback.error)}</p>
        )}
        {missing && <p className="error" role="alert">{t.setup.missing}</p>}
        {passwords && (
          <button type="submit" className="button primary" disabled={setup.isPending || mismatch}>
            {setup.isPending ? t.setup.submitting : t.setup.submit}
          </button>
        )}
        {oidc && passwords && <p className="subtle divider">{t.oidc.or}</p>}
        {oidc && <OidcButton action="continue" path="/v1/setup/oidc" primary={!passwords} body={providerBody} />}
      </form>
    </main>
  );
}
