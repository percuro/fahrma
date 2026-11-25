import { useState, type ChangeEvent, type FormEvent } from 'react';
import { useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, errorText } from '../lib/api';
import type { Group, ImportPreview } from '../lib/types';
import { APP_NAME } from '../app/brand';
import { ME_KEY } from '../hooks/useMe';
import { useSession } from '../hooks/useSession';
import { useFormat } from '../hooks/useFormat';
import { useFeedback } from '../components/feedback-context';
import { useT } from '../i18n';

/** Moving a group here: a "fahrma-group/1" file from the JSON export of another instance. */
export function ImportPage() {
  const t = useT();
  const i = t.import;
  const f = useFormat();
  const me = useSession();
  const { toast } = useFeedback();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [raw, setRaw] = useState('');
  const [member, setMember] = useState<number | null>(null);
  const check = useMutation({
    mutationFn: (text: string) => apiFetch<ImportPreview>('/v1/groups/import/check', { method: 'POST', body: text }),
    onSuccess: (preview) => {
      const candidates = preview.members.filter((m) => m.active && !m.deleted);
      const mine = candidates.find((m) => m.display_name === me.display_name);
      setMember(mine?.user_id ?? (candidates.length === 1 ? candidates[0].user_id : null));
    },
  });
  const run = useMutation({
    mutationFn: () => apiFetch<Group>(`/v1/groups/import?member=${member}`, { method: 'POST', body: raw }),
    onSuccess: (group) => {
      navigate(`/g/${group.id}/group`);
      toast(i.done);
      void queryClient.invalidateQueries({ queryKey: ME_KEY });
    },
  });
  const choose = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    check.reset();
    run.reset();
    setMember(null);
    if (!file) return;
    const text = await file.text();
    setRaw(text);
    check.mutate(text);
  };
  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (member !== null) run.mutate();
  };
  const preview = check.data;
  return (
    <>
      <h1>{i.title}</h1>
      <p>{i.intro(APP_NAME)}</p>
      <form className="card form" onSubmit={submit}>
        <label className="field">
          <span>{i.file}</span>
          <input type="file" accept="application/json,.json" onChange={choose} />
        </label>
        {check.isPending && <p className="subtle m-0" role="status">{i.checking}</p>}
        {check.isError && <p className="error" role="alert">{errorText(check.error)}</p>}
        {preview && (
          <>
            <div>
              <h2 className="mt-0">{preview.name}</h2>
              <p className="m-0">{i.counts(preview.counts.cars, preview.counts.trips, preview.counts.fuel, preview.counts.expenses, preview.counts.settlements)}</p>
              <p className="subtle small m-0">
                {[
                  preview.first_date && preview.last_date && i.period(f.date(preview.first_date), f.date(preview.last_date)),
                  preview.currency,
                  preview.exported_at && i.exported(f.date(preview.exported_at)),
                ].filter(Boolean).join(' · ')}
              </p>
            </div>
            <fieldset>
              <legend>{i.whoAreYou}</legend>
              {preview.members.filter((m) => m.active && !m.deleted).map((m) => (
                <label key={m.user_id} className="check radio">
                  <input type="radio" name="member" checked={member === m.user_id} onChange={() => setMember(m.user_id)} required />
                  <span>{m.display_name}{m.role === 'admin' ? ` · ${t.group.admin}` : ''}</span>
                </label>
              ))}
              <p className="subtle small m-0 mt-05">{i.whoHint}</p>
            </fieldset>
            {run.isError && <p className="error" role="alert">{errorText(run.error)}</p>}
            <button type="submit" className="button primary" disabled={member === null || run.isPending}>
              {run.isPending ? i.importing : i.submit}
            </button>
          </>
        )}
      </form>
    </>
  );
}
