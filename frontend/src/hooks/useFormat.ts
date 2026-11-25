import { useMemo } from 'react';
import { useParams } from 'react-router-dom';
import { useQuery } from '@tanstack/react-query';
import { apiFetch } from '../lib/api';
import { createFormat, type Format } from '../lib/format';
import type { Group } from '../lib/types';
import { useI18n } from '../i18n';
import { groupKey } from './useGroupData';

/** Formatting in the interface language and, inside a group, in the group's currency. */
export function useFormat(): Format {
  const { lang } = useI18n();
  const { groupId } = useParams();
  const gid = Number(groupId);
  const group = useQuery({
    queryKey: [...groupKey(gid), ''],
    queryFn: () => apiFetch<Group>(`/v1/groups/${gid}`),
    enabled: Number.isInteger(gid) && gid > 0,
  });
  const currency = group.data?.currency ?? 'EUR';
  return useMemo(() => createFormat(lang, currency), [lang, currency]);
}
