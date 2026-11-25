import { useState, type FormEvent } from 'react';
import { Navigate, useNavigate } from 'react-router-dom';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { apiFetch, errorText } from '../lib/api';
import type { Group } from '../lib/types';
import { ME_KEY } from '../hooks/useMe';
import { useSession } from '../hooks/useSession';
import { readLastGroup } from '../lib/storage';
import { useT } from '../i18n';

export function StartPage() {
  const t = useT();
  const me = useSession();
  if (me.groups.length > 0) {
    const remembered = readLastGroup();
    const target = me.groups.find((g) => g.id === remembered) ?? me.groups[0];
    return <Navigate to={`/g/${target.id}`} replace />;
  }
  return (
    <>
      <h1>{t.start.welcome}</h1>
      <p>{t.start.intro}</p>
      <CreateGroup />
    </>
  );
}

export function CreateGroup() {
  const t = useT();
  const [name, setName] = useState('');
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const create = useMutation({
    mutationFn: () => apiFetch<Group>('/v1/groups', { method: 'POST', body: JSON.stringify({ name }) }),
    onSuccess: (group) => {
      // Navigate first, then reload "me"; otherwise the start page redirects to the overview first
      navigate(`/g/${group.id}/group`);
      void queryClient.invalidateQueries({ queryKey: ME_KEY });
    },
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate();
  };
  return (
    <form className="card form" onSubmit={submit}>
      <label className="field">
        <span>{t.start.groupName}</span>
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder={t.start.groupNamePlaceholder} required maxLength={80} />
      </label>
      {create.isError && <p className="error" role="alert">{errorText(create.error)}</p>}
      <button type="submit" className="button primary" disabled={create.isPending}>{t.start.create}</button>
    </form>
  );
}
