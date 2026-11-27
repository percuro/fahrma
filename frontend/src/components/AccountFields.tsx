import type { AccountForm } from './account-form';
import { useT } from '../i18n';

/** Name, username and password twice – for registration, invitations and the setup. */
export function AccountFields({ form, passwordOnly = false, withoutPassword = false, passwordLabel }: {
  form: AccountForm;
  passwordOnly?: boolean;
  /** PASSWORD_LOGIN=off: the account logs in through the provider only */
  withoutPassword?: boolean;
  passwordLabel?: string;
}) {
  const t = useT();
  const { values, set } = form;
  return (
    <>
      {!passwordOnly && (
        <>
          <label className="field">
            <span>{t.invite.displayName}</span>
            <input value={values.display_name} onChange={set('display_name')} required maxLength={80} autoComplete="name" />
          </label>
          <label className="field">
            <span>{t.invite.username}</span>
            <input value={values.username} onChange={set('username')} required minLength={3} maxLength={32}
              pattern="[A-Za-z0-9._\-]{3,32}" title={t.auth.usernameHint} autoCapitalize="none" autoComplete="username"
              spellCheck={false} aria-describedby="username-hint" />
            <span id="username-hint" className="hint">{t.auth.usernameHint}</span>
          </label>
        </>
      )}
      {!withoutPassword && (
        <>
          <label className="field">
            <span>{passwordLabel ?? t.invite.password}</span>
            <input type="password" value={values.password} onChange={set('password')} required autoComplete="new-password" />
          </label>
          <label className="field">
            <span>{t.auth.passwordRepeat}</span>
            <input type="password" value={values.repeat} onChange={set('repeat')} required autoComplete="new-password" />
          </label>
        </>
      )}
    </>
  );
}
