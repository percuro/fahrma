export interface GroupBrief {
  id: number;
  name: string;
  role: 'admin' | 'member';
}

export interface Me {
  id: number;
  username: string;
  display_name: string;
  locale: 'de' | 'en' | null;
  role: 'admin' | 'user';
  /** Confirmed address, and one waiting for confirmation */
  email: string | null;
  email_pending: string | null;
  groups: GroupBrief[];
  today: string;
  timezone: string;
}

export interface Member {
  user_id: number;
  username: string;
  display_name: string;
  role: 'admin' | 'member';
  active: boolean;
  /** The account was deleted; its bookings stay under an anonymous name */
  deleted: boolean;
  /** A person without an account (imported or added by an admin) */
  placeholder: boolean;
  /** Admins only: until when the open personal link of a placeholder works */
  link_expires_at: string | null;
}

export interface Group {
  id: number;
  name: string;
  currency: string;
  timezone: string | null;
  effective_timezone: string;
  today: string;
  my_role: 'admin' | 'member';
  members: Member[];
}

export type EnergyUnit = 'l' | 'kWh';

export interface Car {
  id: number;
  name: string;
  plate: string | null;
  start_odometer_km: number;
  energy_unit: EnergyUnit;
  archived: boolean;
  last_km: number;
  open_trip_id: number | null;
}

export interface Share {
  user_id: number;
  weight: number;
}

export interface ExternalPayment {
  id?: number;
  payer_name: string;
  amount_cents: number;
  received_by_user_id: number;
}

export interface Trip {
  id: number;
  car_id: number;
  date: string;
  start_km: number;
  end_km: number | null;
  km: number | null;
  note: string | null;
  shares: Share[];
  external: ExternalPayment[];
  created_by: number;
  settlement_id: number | null;
  cost_cents: number | null;
  cost_is_estimate: boolean;
}

export interface TripWrite {
  car_id: number;
  date: string;
  start_km: number;
  end_km: number | null;
  note: string | null;
  shares: Share[];
  external: ExternalPayment[];
}

export interface FuelWrite {
  car_id: number;
  date: string;
  odometer_km: number | null;
  /** thousandths of the car's energy unit (ml or Wh) */
  quantity_milli: number | null;
  amount_cents: number;
  paid_by_user_id: number;
  full_tank: boolean;
  note: string | null;
}

export interface Fuel extends FuelWrite {
  id: number;
  created_by: number;
  settlement_id: number | null;
}

export type Allocation = 'by_km' | 'equal' | 'single' | 'trip';

export interface ExpenseWrite {
  car_id: number | null;
  trip_id: number | null;
  date: string;
  category: string;
  description: string | null;
  amount_cents: number;
  paid_by_user_id: number;
  allocation: Allocation;
  allocated_user_id: number | null;
}

export interface Expense extends ExpenseWrite {
  id: number;
  created_by: number;
  settlement_id: number | null;
}

export interface BalanceWarning {
  code: 'km_gap' | 'carried_fuel' | 'carried_expense' | 'open_trip';
  message: string;
  params?: Record<string, unknown>;
  car_id: number | null;
  from_km: number | null;
  to_km: number | null;
  blocking: boolean;
}

export interface CarBalance {
  car_id: number;
  name: string;
  km: number;
  fuel_cents: number;
  rate_cents_per_km: number | null;
  last_rate_cents_per_km: number | null;
  carried_fuel_cents: number;
}

export interface MemberBalance {
  user_id: number;
  display_name: string;
  km: number;
  paid_cents: number;
  trip_cost_cents: number;
  external_credit_cents: number;
  external_held_cents: number;
  expense_cost_cents: number;
  balance_cents: number;
}

export interface Transfer {
  id: number | null;
  from_user_id: number;
  to_user_id: number;
  amount_cents: number;
  paid_at: string | null;
  settlement_id: number | null;
}

export interface Balance {
  period_start: string | null;
  period_end: string;
  cars: CarBalance[];
  members: MemberBalance[];
  transfers: Transfer[];
  warnings: BalanceWarning[];
  trip_count: number;
  fuel_count: number;
  expense_count: number;
  total_cost_cents: number;
}

export interface Settlement {
  id: number;
  period_start: string | null;
  period_end: string;
  created_by: number;
  created_at: string;
  result: Balance;
  transfers: Transfer[];
  is_latest: boolean;
}

export interface SettlementBrief {
  id: number;
  period_start: string | null;
  period_end: string;
  created_at: string;
  total_cost_cents: number;
  open_transfers: number;
}

export interface AuditEntry {
  id: number;
  user_id: number;
  entity: string;
  entity_id: number;
  action: string;
  diff: Record<string, unknown> | null;
  created_at: string;
}

export interface Meta {
  version: string;
  registration: 'invite' | 'open';
  setup_needed: boolean;
  links: { imprint_url: string | null; privacy_url: string | null; terms_url: string | null };
  limits: { groups_per_user: number | null; members_per_group: number | null; cars_per_group: number | null };
  /** E-mail is set up: forgotten password, addresses, links by mail */
  mail: boolean;
}

export interface DeviceSession {
  id: number;
  created_at: string;
  last_seen_at: string | null;
  device: string | null;
  current: boolean;
}

export interface DeletionPreview {
  groups_deleted: { id: number; name: string }[];
  admin_handover: { group_id: number; group_name: string; new_admin_name: string }[];
  groups_kept: { id: number; name: string }[];
}

export interface AdminUser {
  id: number;
  username: string;
  display_name: string;
  email: string | null;
  role: 'admin' | 'user';
  is_active: boolean;
  created_at: string;
  last_seen_at: string | null;
  group_count: number;
}

export interface InvitationCreated {
  id: number;
  purpose: 'signup' | 'password_reset';
  url: string;
  expires_at: string;
  email_sent: boolean;
}

export interface GroupInviteCreated {
  url: string;
  expires_at: string;
  email_sent: boolean;
}

export interface InvitationRead {
  id: number;
  purpose: 'signup' | 'password_reset';
  role: 'admin' | 'user' | null;
  note: string | null;
  email: string | null;
  target_username: string | null;
  created_by_username: string | null;
  created_at: string;
  expires_at: string;
}

/** Open registration with e-mail: the account follows once the link in the mail is used */
export interface RegistrationPending {
  email: string;
}

export type InvitationKind = 'group' | 'signup' | 'password_reset' | 'verify_email' | 'registration';

export interface InvitationInfo {
  kind: InvitationKind;
  group_name: string | null;
  /** Personal group link: the member without an account whose place it takes over */
  member_name: string | null;
  username: string | null;
  /** verify_email, registration: the address being confirmed */
  email: string | null;
  expires_at: string;
}

export interface ImportPreview {
  app_version: string | null;
  exported_at: string | null;
  name: string;
  currency: string;
  timezone: string | null;
  members: { user_id: number; display_name: string; role: 'admin' | 'member'; active: boolean; deleted: boolean }[];
  counts: { cars: number; trips: number; fuel: number; expenses: number; settlements: number };
  first_date: string | null;
  last_date: string | null;
}
