import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useParams } from 'react-router-dom';
import { apiFetch } from '../lib/api';
import type {
  AuditEntry,
  Balance,
  Car,
  CarStats,
  Expense,
  Fuel,
  Group,
  Reservation,
  Settlement,
  SettlementBrief,
  Transfer,
  Trip,
} from '../lib/types';

export function useGroupId(): number {
  const { groupId } = useParams();
  return Number(groupId);
}

/** Whether the group id in the URL is a usable number (not "abc" or a leftover path). */
export const isValidGroupId = (gid: number) => Number.isInteger(gid) && gid > 0;

export const groupKey = (gid: number) => ['group', gid] as const;

function useGroupQuery<T>(path: string, enabled = true) {
  const gid = useGroupId();
  return useQuery({
    queryKey: [...groupKey(gid), path],
    queryFn: () => apiFetch<T>(`/v1/groups/${gid}${path}`),
    enabled: isValidGroupId(gid) && enabled,
  });
}

export const useGroup = () => useGroupQuery<Group>('');
export const useCars = () => useGroupQuery<Car[]>('/cars');
export const useTrips = () => useGroupQuery<Trip[]>('/trips');
export const useFuel = () => useGroupQuery<Fuel[]>('/fuel');
export const useExpenses = () => useGroupQuery<Expense[]>('/expenses');
export const useOpenTransfers = () => useGroupQuery<Transfer[]>('/transfers/open');
export const useSettlements = () => useGroupQuery<SettlementBrief[]>('/settlements');
export const useAudit = () => useGroupQuery<AuditEntry[]>('/audit');
export const useSettlement = (id: number) => useGroupQuery<Settlement>(`/settlements/${id}`);
/** One trip; starts from the trip list (also from the offline cache) and is refreshed from the server. */
export function useTrip(id: number | null) {
  const gid = useGroupId();
  const queryClient = useQueryClient();
  const listKey = [...groupKey(gid), '/trips'];
  return useQuery({
    queryKey: [...groupKey(gid), `/trips/${id}`],
    queryFn: () => apiFetch<Trip>(`/v1/groups/${gid}/trips/${id}`),
    enabled: isValidGroupId(gid) && id !== null,
    initialData: () => queryClient.getQueryData<Trip[]>(listKey)?.find((trip) => trip.id === id),
    initialDataUpdatedAt: () => queryClient.getQueryState(listKey)?.dataUpdatedAt,
  });
}
export const useFuelEntry = (id: number | null) => useGroupQuery<Fuel>(`/fuel/${id}`, id !== null);
export const useExpense = (id: number | null) => useGroupQuery<Expense>(`/expenses/${id}`, id !== null);
export const useCarStats = (carId: number | null, year: number | null) =>
  useGroupQuery<CarStats>(`/cars/${carId}/stats${year ? `?year=${year}` : ''}`, carId !== null);
/** Reservations overlapping the local days from..to (default: today and the next 13 days). */
export function useReservations(range?: { from: string; to: string }, carId?: number | null) {
  const query = new URLSearchParams({ ...(range ?? {}), ...(carId ? { car_id: String(carId) } : {}) }).toString();
  return useGroupQuery<Reservation[]>(`/reservations${query ? `?${query}` : ''}`);
}
export const useReservation = (id: number | null) => useGroupQuery<Reservation>(`/reservations/${id}`, id !== null);
export const useBalance = (periodEnd?: string) =>
  useGroupQuery<Balance>(`/balance${periodEnd ? `?period_end=${periodEnd}` : ''}`);

/** Write to the group, then reload all group data (balances depend on everything). */
export function useGroupMutation<TVars, TResult = unknown>(
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE',
  path: (vars: TVars) => string,
  body?: (vars: TVars) => unknown,
) {
  const gid = useGroupId();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (vars: TVars) =>
      apiFetch<TResult>(`/v1/groups/${gid}${path(vars)}`, {
        method,
        body: body ? JSON.stringify(body(vars)) : undefined,
      }),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: groupKey(gid) }),
  });
}

export function useMemberNames(): (id: number | null | undefined) => string {
  const group = useGroup();
  const names = new Map(group.data?.members.map((m) => [m.user_id, m.display_name]) ?? []);
  return (id) => (id === null || id === undefined ? '–' : (names.get(id) ?? '?'));
}
