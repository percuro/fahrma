import { useNavigate } from 'react-router-dom';
import { errorText } from '../lib/api';
import { draftError, removeDraft, type Draft } from '../lib/outbox';
import { useGroupId } from '../hooks/useGroupData';
import { useT } from '../i18n';
import { useFeedback } from './feedback-context';

/** Top of a form opened from a draft: what it is and, if the server refused it, why. */
export function DraftNotice({ draft }: { draft: Draft }) {
  const t = useT();
  const error = draftError(draft);
  return (
    <div className={`notice${error ? ' error-box' : ''}`} role={error ? 'alert' : undefined}>
      <p className="m-0">{error ? t.offline.refused(errorText(error)) : t.offline.draftNotice}</p>
    </div>
  );
}

export function DiscardDraftButton({ draft }: { draft: Draft }) {
  const t = useT();
  const gid = useGroupId();
  const navigate = useNavigate();
  const { toast, confirm } = useFeedback();
  const discard = async () => {
    if (!(await confirm(t.offline.confirmDiscard, { confirmLabel: t.offline.discard, danger: true }))) return;
    removeDraft(draft.id);
    toast(t.offline.discarded);
    navigate(`/g/${gid}`);
  };
  return (
    <button type="button" className="button danger push-end" onClick={discard}>{t.offline.discard}</button>
  );
}
