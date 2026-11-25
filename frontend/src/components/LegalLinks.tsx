import { useMeta } from '../hooks/useMeta';
import { useT } from '../i18n';

/** Imprint, privacy policy and terms of the operator, when configured (IMPRINT_URL …). */
export function LegalLinks() {
  const t = useT();
  const meta = useMeta();
  const links = meta.data?.links;
  if (!links) return null;
  const items = [
    [links.imprint_url, t.legal.imprint],
    [links.privacy_url, t.legal.privacy],
    [links.terms_url, t.legal.terms],
  ].filter((item): item is [string, string] => !!item[0]);
  if (items.length === 0) return null;
  return (
    <nav className="legal-links" aria-label={t.legal.imprint}>
      {items.map(([url, label]) => (
        <a key={url} href={url} target="_blank" rel="noopener noreferrer">{label}</a>
      ))}
    </nav>
  );
}
