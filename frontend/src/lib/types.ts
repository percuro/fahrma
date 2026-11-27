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
  /** false: logs in through the OIDC provider only (since 0.11) */
  has_password?: boolean;
  oidc?: OidcLink | null;
}

/** The account's link to the OIDC provider, as the provider last described it */
export interface OidcLink {
  email: string | null;
  preferred_username: string | null;
  linked_at: string;
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
  /** Since 0.9; missing in group data a device kept from an older version */
  plan?: GroupPlan;
}

/** A plan's name: one text, or one per language ({"de": "Gratis", "en": "Free"}). */
export type PlanName = string | Record<string, string>;

export interface PlanInfo {
  id: string;
  name: PlanName;
  /** null = unlimited */
  members_per_group: number | null;
  cars_per_group: number | null;
  /** Megabytes of receipt photos; since 0.10 */
  receipt_mb_per_group?: number | null;
}

export interface PlanUsage {
  members_per_group: number;
  cars_per_group: number;
  /** Megabytes, one decimal; since 0.10 */
  receipt_mb_per_group?: number;
}

/** The plan in force for a group. */
export interface GroupPlan extends PlanInfo {
  /** Last day of the group's own plan; null = no end */
  until: string | null;
  usage: PlanUsage;
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

/** A receipt photo; the image is at /groups/{group}/receipts/{id}. */
export interface Receipt {
  id: number;
  content_type: string;
  bytes: number;
  width: number;
  height: number;
  created_by: number;
  created_at: string;
}

export interface Fuel extends FuelWrite {
  id: number;
  created_by: number;
  settlement_id: number | null;
  /** Since 0.10; missing in data a device kept from an older version */
  receipts?: Receipt[];
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
  /** Since 0.10; missing in data a device kept from an older version */
  receipts?: Receipt[];
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
  limits: {
    groups_per_user: number | null;
    members_per_group: number | null;
    cars_per_group: number | null;
    receipt_mb_per_group?: number | null;
  };
  /** E-mail is set up: forgotten password, addresses, links by mail */
  mail: boolean;
  /** Web Push: the key for subscribing; null = push notifications are off on this instance */
  vapid_public_key: string | null;
  /** Plans groups can have; null = this instance has no plans */
  plans?: PlanInfo[] | null;
  /** The plan of every group without its own */
  default_plan?: string | null;
  /** Group admins can change their plan (the operator set up a page for it) */
  billing?: boolean;
  /** Accounts unused for this many months are deleted after a warning; null = never */
  inactive_delete_months?: number | null;
  /** Receipt photos can be attached (since 0.10; missing = off) */
  receipts?: boolean;
  /** Passwords can be used (since 0.11; missing = yes) */
  password_login?: boolean;
  /** Login through an OIDC provider; null = not set up. label: name on the button */
  oidc?: { label: string | null } | null;
}

export interface DeviceSession {
  id: number;
  created_at: string;
  last_seen_at: string | null;
  device: string | null;
  current: boolean;
  /** How the session was started (since 0.11) */
  auth_method?: 'password' | 'oidc';
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
  /** The day a warned, unused account will be deleted */
  deletion_due?: string | null;
  /** Since 0.11: false = logs in through the OIDC provider only */
  has_password?: boolean;
  oidc_linked?: boolean;
}

/** A group as instance admins see it: plan and counts, never entries or amounts. */
export interface AdminGroup {
  id: number;
  name: string;
  created_at: string;
  last_activity_at: string | null;
  /** The group's own plan as stored; it may have run out (see effective_plan) */
  plan: string | null;
  plan_until: string | null;
  plan_note: string | null;
  effective_plan: string;
  usage: PlanUsage;
  admins: { user_id: number; display_name: string }[];
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
  counts: { cars: number; trips: number; fuel: number; expenses: number; settlements: number; receipts?: number };
  first_date: string | null;
  last_date: string | null;
}

export interface CarStats {
  car_id: number;
  energy_unit: EnergyUnit;
  year: number | null;
  years: number[];
  km: number;
  trips: number;
  fuel_cents: number;
  fuel_entries: number;
  /** Entries with a quantity, for the average price per litre or kWh */
  priced_milli: number;
  priced_cents: number;
  /** Sums over the intervals between two full tanks that end in the period */
  consumption: { milli: number; km: number; cents: number; intervals: number } | null;
  expense_cents: number;
  categories: { category: string; cents: number }[];
  members: { user_id: number; km: number }[];
  /** Months of the year ("2026-03"), or the years ("2026") */
  periods: { period: string; km: number; fuel_cents: number; expense_cents: number }[];
}

/** Times are wall-clock times in the group's time zone ("2026-12-01T08:00:00"), plus the same moments in UTC. */
export interface Reservation {
  id: number;
  car_id: number;
  user_id: number;
  starts_at: string;
  ends_at: string;
  starts_at_utc: string;
  ends_at_utc: string;
  note: string | null;
  created_by: number;
}

export interface ReservationWrite {
  car_id: number;
  user_id: number;
  starts_at: string;
  ends_at: string;
  note: string | null;
}

export interface NotifySettings {
  reservation_reminder: boolean;
  lead_minutes: 15 | 60 | 180;
  reservation_changes: boolean;
  open_trip: boolean;
  settlements: boolean;
}

export interface NotificationsState {
  settings: NotifySettings;
  /** This login receives push notifications */
  this_device: boolean;
  devices: number;
}

/** Security log (since 0.12): logins and changes to accounts */
export type SecurityDetails = Record<string, string | number | boolean | null>;

export interface SecurityEvent {
  id: number;
  created_at: string;
  event: string;
  actor_user_id: number | null;
  actor_username: string | null;
  target_user_id: number | null;
  target_username: string | null;
  /** Only for failed attempts and blocks, shortened: IPv4 /24, IPv6 /48 */
  ip_prefix: string | null;
  details: SecurityDetails;
}

export interface SecurityEventPage {
  events: SecurityEvent[];
  next_before_id: number | null;
  /** SECURITY_LOG_DAYS: how long entries are kept */
  retention_days: number;
}

/** An entry about the own account; an instance admin who acted stays unnamed */
export interface OwnSecurityEvent {
  id: number;
  created_at: string;
  event: string;
  actor: 'self' | 'admin' | null;
  ip_prefix: string | null;
  details: SecurityDetails;
}

export interface OwnSecurityEventPage {
  events: OwnSecurityEvent[];
  next_before_id: number | null;
}
