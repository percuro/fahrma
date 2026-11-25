import { useState } from 'react';
import { APP_NAME } from '../app/brand';
import { useFormat } from '../hooks/useFormat';
import { useT } from '../i18n';

/** A one-time link that was just created: share or copy it, with its validity and where it was sent. */
export function LinkBox({ url, expiresAt, sentTo, label, onNew }: {
  url: string;
  expiresAt: string;
  sentTo?: string | null;
  label: string;
  onNew?: () => void;
}) {
  const g = useT().group;
  const f = useFormat();
  const [copied, setCopied] = useState(false);
  const share = async () => {
    try {
      if (navigator.share) {
        await navigator.share({ title: g.shareTitle(APP_NAME), url });
        return;
      }
      await navigator.clipboard.writeText(url);
      setCopied(true);
    } catch {
      // Sharing cancelled or not allowed; the field stays selectable
    }
  };
  return (
    <div className="form">
      {sentTo && <p className="m-0" role="status">{g.sentTo(sentTo)}</p>}
      <input readOnly value={url} onFocus={(e) => e.target.select()} aria-label={label} />
      <div className="button-row mt-0">
        <button type="button" className="button primary" onClick={share}>{copied ? g.copied : g.share}</button>
        {onNew && <button type="button" className="button" onClick={() => { setCopied(false); onNew(); }}>{g.newLink}</button>}
      </div>
      <p className="subtle small m-0">{g.validUntil(f.date(expiresAt))}</p>
    </div>
  );
}
