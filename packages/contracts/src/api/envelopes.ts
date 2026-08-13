export interface SuccessEnvelope<T, M = Record<string, never>> {
  data: T;
  meta?: M;
}

export interface ErrorDetail {
  code: string;
  message: string;
  fields?: Record<string, string>;
}

export interface ErrorEnvelope {
  error: ErrorDetail;
}

export interface PaginationMeta {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
}
