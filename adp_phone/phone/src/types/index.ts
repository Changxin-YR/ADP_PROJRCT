// ============================================================
// Core Types for ADP Fish Pond Aquaculture Management
// Aligned with the ADP backend selected through EXPO_PUBLIC_API_BASE_URL.
// ============================================================

// --- API Response Wrapper ---
export interface ApiResponse<T> {
  code: string; // 'OK', 'FORBIDDEN', 'UNAUTHENTICATED', etc.
  message?: string;
  data: T;
}

export interface PaginatedData<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

// --- Auth ---
export interface User {
  id: number;
  login_name: string;
  name: string;
  phone?: string;
  status: 'pending' | 'rejected' | 'active' | 'disabled' | 'must_change_password' | 'retired';
  roles: Role[];
  permissions: string[];
  data_scopes: DataScope[];
  organization_id: number;
  farm_id?: number;
  created_at: string;
  updated_at: string;
}

export interface Role {
  id: number;
  code: string;
  name: string;
}

export interface DataScope {
  id: number;
  code: string;
  name: string;
  scope_type: 'farm' | 'area' | 'personal';
  area_id?: number;
}

export type UserRoleCode =
  | 'super_admin'
  | 'breed_manager'
  | 'breed_worker'
  | 'warehouse_manager'
  | 'purchaser'
  | 'finance_staff'
  | 'sales_staff';

// --- Pond ---
export type PondStatus = 'build' | 'stocked' | 'farming' | 'rest' | 'clean' | 'rebuild';

export const POND_STATUS_LABELS: Record<PondStatus, string> = {
  build: '筹建',
  stocked: '放养',
  farming: '养殖',
  rest: '轮休',
  clean: '清塘',
  rebuild: '改造',
};

export const POND_STATUS_COLORS: Record<PondStatus, string> = {
  build: '#FF9500',
  stocked: '#5AC8FA',
  farming: '#34C759',
  rest: '#8E8E93',
  clean: '#AF52DE',
  rebuild: '#FF3B30',
};

export interface Pond {
  id: number;
  code: string;
  name: string;
  area_id: number;
  farm_id: number;
  organization_id: number;
  pond_group_id?: number;
  capacity_mu: number;
  species: string;
  manager_name: string;
  pond_status: PondStatus;
  location_text?: string;
  description?: string;
  version: number;
  status: DocumentStatus;
  created_at: string;
  updated_at: string;
  // Joined/computed fields returned by detail API
  depth?: number;
  water_source?: string;
  group_name?: string;
  water_temp?: number;
  ph?: number;
  dissolved_oxygen?: number;
  ammonia?: number;
}

// --- Document Lifecycle ---
export type DocumentStatus = 'draft' | 'submitted' | 'verified' | 'confirmed' | 'corrected' | 'archived';

export const DOCUMENT_STATUS_LABELS: Record<string, string> = {
  draft: '草稿',
  submitted: '已提交',
  verified: '已核验',
  confirmed: '已确认',
  corrected: '已更正',
  archived: '已归档',
};

export const DOCUMENT_STATUS_COLORS: Record<string, string> = {
  draft: '#8E8E93',
  submitted: '#FF9500',
  verified: '#34C759',
  confirmed: '#007AFF',
  corrected: '#AF52DE',
  archived: '#636366',
};

// --- Materials ---
export interface Material {
  id: number;
  code: string;
  name: string;
  category: string;
  unit: string;
  specification?: string;
  safety_stock: number;
  shelf_life_days?: number;
  default_supplier_id?: number;
  version: number;
  status: DocumentStatus;
  organization_id: number;
  farm_id?: number;
  area_id?: number;
}

// --- Supplier ---
export interface Supplier {
  id: number;
  code: string;
  name: string;
  contact_name?: string;
  phone?: string;
  address?: string;
  settlement_days: number;
  credit_limit?: number;
  note?: string;
  version: number;
  status: DocumentStatus;
}

// --- Customer ---
export interface Customer {
  id: number;
  code: string;
  name: string;
  contact_name?: string;
  phone?: string;
  address?: string;
  settlement_days: number;
  credit_limit?: number;
  note?: string;
  version: number;
  status: DocumentStatus;
}

// --- Production Batch ---
export interface Batch {
  id: number;
  code: string;
  name: string;
  pond_id: number;
  species: string;
  initial_quantity: number;
  initial_weight_kg: number;
  stocked_at?: string;
  expected_harvest_date?: string;
  batch_status?: string;
  note?: string;
  version: number;
  status: DocumentStatus;
  created_at: string;
  // Joined/computed fields
  pond_name?: string;
  start_date?: string;
  days_elapsed?: number;
}

// --- Feed Plan ---
export interface FeedPlan {
  id: number;
  code: string;
  name: string;
  pond_id?: number;
  batch_id?: number;
  material_id?: number;
  planned_at?: string;
  note?: string;
  payload?: Record<string, unknown>;
  version: number;
  status: DocumentStatus;
  created_at: string;
  // Joined/computed fields
  pond_name?: string;
  start_date?: string;
  daily_amount?: number;
  frequency?: number;
  feed_type?: string;
}

// --- Feed Task ---
export interface FeedTask {
  id: number;
  code: string;
  name: string;
  pond_id?: number;
  batch_id?: number;
  feed_plan_id?: number;
  assigned_user_id?: number;
  material_id?: number;
  quantity?: number;
  weight_kg?: number;
  planned_at?: string;
  happened_at?: string;
  note?: string;
  version: number;
  status: DocumentStatus;
  created_at: string;
  // Joined/computed fields
  pond_name?: string;
  feed_amount?: number;
  scheduled_time?: string;
}

// --- Feed Log ---
export interface FeedLog {
  id: number;
  code: string;
  name: string;
  pond_id?: number;
  batch_id?: number;
  feed_task_id?: number;
  material_id?: number;
  quantity?: number;
  weight_kg?: number;
  happened_at?: string;
  note?: string;
  version: number;
  status: DocumentStatus;
  created_at: string;
  // Joined/computed fields
  pond_name?: string;
  feed_name?: string;
  feed_type?: string;
  actual_amount?: number;
  amount?: number;
  feed_time?: string;
  operator_name?: string;
}

// --- Daily Operation ---
export interface DailyOperation {
  id: number;
  code: string;
  name: string;
  pond_id?: number;
  batch_id?: number;
  happened_at?: string;
  payload?: Record<string, unknown>;
  note?: string;
  version: number;
  status: DocumentStatus;
  created_at: string;
  // Joined/computed fields
  operation_type?: string;
  operation_date?: string;
  pond_name?: string;
  description?: string;
  observations?: string;
}

// --- Warehouse ---
export interface WarehouseDocument {
  id: number;
  code: string;
  name: string;
  document_type: string;
  pond_id?: number;
  material_id?: number;
  quantity?: number;
  note?: string;
  version: number;
  status: DocumentStatus;
  created_at: string;
}

// --- Stock Alert ---
export interface StockAlert {
  warehouse_id: number;
  inventory_lot_id: number;
  material_id: number;
  material_name: string;
  lot_no?: string;
  warehouse_name: string;
  current_quantity: number;
  expiry_date?: string;
  alert_type: 'expired' | 'expiring' | 'low_stock';
  severity: 'high' | 'medium';
  alert_key: string;
  status: 'pending' | 'handled';
  action_code?: string;
  resolution_note?: string;
}

// --- Purchase Order ---
export interface PurchaseOrder {
  id: number;
  code: string;
  name: string;
  supplier_id?: number;
  status: string; // draft, submitted, approved, partially_received, fully_received, cancelled
  version: number;
  created_at: string;
}

// --- Sales Order ---
export interface SalesOrder {
  id: number;
  code: string;
  name: string;
  customer_id?: number;
  pond_id?: number;
  batch_id?: number;
  species?: string;
  quantity?: number;
  unit?: string;
  unit_price?: number;
  sold_at?: string;
  due_date?: string;
  status: string;
  version: number;
  created_at: string;
}

// --- Cost ---
export interface CostEntry {
  id: number;
  category_code: string;
  category_name: string;
  amount: number;
  occurred_on: string;
  period_start: string;
  period_end: string;
  cost_nature: 'direct' | 'public';
  source_type?: string;
  note?: string;
  status: DocumentStatus;
  version: number;
  created_at: string;
}

export const COST_CATEGORIES = [
  { code: 'pond_rent', name: '塘租' },
  { code: 'equipment', name: '设备' },
  { code: 'infrastructure', name: '基础建设' },
  { code: 'labor', name: '人工' },
  { code: 'electricity', name: '电费' },
  { code: 'seed', name: '苗种' },
  { code: 'feed', name: '饲料' },
  { code: 'health', name: '动保' },
  { code: 'other', name: '其他' },
] as const;

// --- Workbench ---
export interface WorkbenchSummary {
  kpis: Record<string, number>;
  work_items: WorkItem[];
  notifications: AppNotification[];
  pond_status_distribution?: Record<PondStatus, number>;
}

export interface WorkItem {
  id: number;
  title: string;
  description?: string;
  priority: 'high' | 'medium' | 'low';
  status: 'pending' | 'claimed' | 'in_progress' | 'completed' | 'cancelled';
  domain_type?: string;
  domain_id?: number;
  created_at: string;
}

export interface AppNotification {
  id: number;
  title: string;
  body: string;
  type: string;
  priority: 'high' | 'medium' | 'low';
  status: 'unread' | 'read' | 'closed';
  created_at: string;
}

// --- Data Exchange ---
export interface DataTemplate {
  id: number;
  code: string;
  name: string;
  entity_type?: string;
  group?: string;
  version?: string;
  description?: string;
  importable?: boolean;
}

export interface RegistrationOptions {
  roles: { id: number; code: string; name: string; description?: string }[];
  areas: { id: number; code: string; name: string }[];
  data_scopes: { id: number; code: string; name: string; scope_type: 'farm' | 'area' | 'personal'; area_id?: number | null; area_name?: string | null }[];
}

export interface RegistrationRequest {
  phone: string;
  name: string;
  password: string;
  confirm_password: string;
  desired_role_id: number;
  desired_scope_type: 'farm' | 'area' | 'personal';
  area_id: number;
  application_note: string;
}

export interface RegistrationResult {
  user: Pick<User, 'id' | 'name' | 'status'>;
  application: Record<string, unknown>;
  status: 'pending';
  next_path: string;
  session?: { expires_at: string; token?: string };
}
